/* Forge 1.0 implementation: lexer, parser, static checker, interpreter and
   builtins. See forge.h for the public API and docs/forge-language.md for the
   language. Pure C, no dependencies beyond libc and libm.

   Memory: every node, string, list, map and environment is allocated from an
   arena that is released all at once when the program or run ends. Runtime
   allocations are capped at FORGE_MAX_HEAP, so a runaway program fails with an
   error instead of exhausting the device. */

#define _DEFAULT_SOURCE

#include "forge.h"

#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* ---------- arena ---------- */

struct arena {
    void **blocks;
    size_t n, cap;
    size_t bytes;
    size_t limit; /* 0 means unlimited */
};

static void *arena_alloc(struct arena *a, size_t size) {
    if (a->limit && a->bytes + size > a->limit) return NULL;
    void *p = calloc(1, size ? size : 1);
    if (!p) return NULL;
    if (a->n == a->cap) {
        size_t nc = a->cap ? a->cap * 2 : 64;
        void **nb = realloc(a->blocks, nc * sizeof *nb);
        if (!nb) { free(p); return NULL; }
        a->blocks = nb;
        a->cap = nc;
    }
    a->blocks[a->n++] = p;
    a->bytes += size;
    return p;
}

static void arena_free(struct arena *a) {
    for (size_t i = 0; i < a->n; i++) free(a->blocks[i]);
    free(a->blocks);
    memset(a, 0, sizeof *a);
}

static char *arena_strndup(struct arena *a, const char *s, size_t n) {
    char *d = arena_alloc(a, n + 1);
    if (d) memcpy(d, s, n);
    return d;
}

/* ---------- AST ---------- */

typedef enum {
    N_INT, N_FLT, N_STR, N_BOOL, N_NIL, N_IDENT, N_LIST, N_MAP,
    N_UNARY, N_BINARY, N_AND, N_OR, N_CALL, N_INDEX, N_LAMBDA,
    N_LET, N_ASSIGN, N_IF, N_WHILE, N_FOR, N_RETURN, N_BREAK, N_CONTINUE,
    N_EXPR, N_BLOCK, N_FN, N_IMPORT
} node_kind;

enum op { OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_MOD, OP_EQ, OP_NE, OP_LT, OP_LE, OP_GT, OP_GE, OP_NEG, OP_NOT };

typedef struct node node;
struct node {
    node_kind kind;
    int line, col, file;
    int op;
    int64_t ival;
    double fval;
    char *name;      /* identifier, string value, fn/let/for name, import path */
    size_t slen;     /* string literal length */
    node *a, *b, *c; /* children; meaning depends on kind */
    node **kids;     /* args, list items, map pairs, block statements, top-level decls */
    size_t nkids, kcap;
    char **params;
    size_t nparams;
};

static void kid_push(struct arena *ar, node *n, node *kid) {
    if (n->nkids == n->kcap) {
        size_t nc = n->kcap ? n->kcap * 2 : 4;
        node **nk = arena_alloc(ar, nc * sizeof *nk);
        if (!nk) return;
        if (n->nkids) memcpy(nk, n->kids, n->nkids * sizeof *nk);
        n->kids = nk;
        n->kcap = nc;
    }
    n->kids[n->nkids++] = kid;
}

/* ---------- compile-time state and errors ---------- */

struct program_files {
    char *path[FORGE_MAX_FILES];
    size_t n;
};

struct forge_program {
    struct arena ar;
    node *root;                    /* N_BLOCK of merged top-level declarations */
    struct program_files files;
};

struct cx {
    struct arena *ar;
    const char *src;
    size_t n, pos;
    int line, col;
    int file;
    jmp_buf *jb;
    char msg[FORGE_MSG_MAX];
    int eline, ecol;
};

__attribute__((noreturn)) static void cx_fail(struct cx *c, int line, int col, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(c->msg, sizeof c->msg, fmt, ap);
    va_end(ap);
    c->eline = line;
    c->ecol = col;
    longjmp(*c->jb, 1);
}

/* ---------- tokens ---------- */

typedef enum { TK_EOF, TK_IDENT, TK_INT, TK_FLT, TK_STR, TK_OP } tok_kind;

typedef struct {
    tok_kind k;
    char *text; /* identifier, operator, or decoded string */
    size_t tlen;
    int64_t iv;
    double fv;
    int line, col;
} token;

static const char *const keywords[] = {
    "let", "fn", "if", "else", "while", "for", "in", "return", "break", "continue",
    "true", "false", "nil", "and", "or", "not", "import", NULL,
};

static int is_keyword(const char *s) {
    for (size_t i = 0; keywords[i]; i++) if (!strcmp(keywords[i], s)) return 1;
    return 0;
}

struct tokvec { token *t; size_t n, cap; };

static void tok_push(struct cx *c, struct tokvec *v, token t) {
    if (v->n == v->cap) {
        size_t nc = v->cap ? v->cap * 2 : 256;
        token *nt = realloc(v->t, nc * sizeof *nt);
        if (!nt) cx_fail(c, t.line, t.col, "out of memory while reading source");
        v->t = nt;
        v->cap = nc;
    }
    v->t[v->n++] = t;
}

static int cur_char(struct cx *c) { return c->pos < c->n ? (unsigned char)c->src[c->pos] : -1; }
static int peek_char(struct cx *c, size_t ahead) {
    return c->pos + ahead < c->n ? (unsigned char)c->src[c->pos + ahead] : -1;
}

static void advance(struct cx *c) {
    if (c->pos < c->n) {
        if (c->src[c->pos] == '\n') { c->line++; c->col = 1; }
        else c->col++;
        c->pos++;
    }
}

static void lex(struct cx *c, struct tokvec *v) {
    c->line = 1;
    c->col = 1;
    for (;;) {
        int ch = cur_char(c);
        if (ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n') { advance(c); continue; }
        if (ch == '/' && peek_char(c, 1) == '/') {
            while (cur_char(c) != -1 && cur_char(c) != '\n') advance(c);
            continue;
        }
        token t;
        memset(&t, 0, sizeof t);
        t.line = c->line;
        t.col = c->col;
        if (ch == -1) { t.k = TK_EOF; tok_push(c, v, t); return; }

        if (ch == '_' || (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z')) {
            size_t start = c->pos;
            while (cur_char(c) == '_' || isalnum(cur_char(c))) advance(c);
            t.k = TK_IDENT;
            t.tlen = c->pos - start;
            t.text = arena_strndup(c->ar, c->src + start, t.tlen);
            if (!t.text) cx_fail(c, t.line, t.col, "out of memory while reading source");
            tok_push(c, v, t);
            continue;
        }
        if (ch >= '0' && ch <= '9') {
            size_t start = c->pos;
            while (cur_char(c) >= '0' && cur_char(c) <= '9') advance(c);
            int is_float = 0;
            if (cur_char(c) == '.' && peek_char(c, 1) >= '0' && peek_char(c, 1) <= '9') {
                is_float = 1;
                advance(c);
                while (cur_char(c) >= '0' && cur_char(c) <= '9') advance(c);
            }
            if (isalpha(cur_char(c)) || cur_char(c) == '_')
                cx_fail(c, t.line, t.col, "invalid number literal");
            char buf[64];
            size_t len = c->pos - start;
            if (len >= sizeof buf) cx_fail(c, t.line, t.col, "number literal is too long");
            memcpy(buf, c->src + start, len);
            buf[len] = '\0';
            if (is_float) {
                t.k = TK_FLT;
                t.fv = strtod(buf, NULL);
                if (!isfinite(t.fv)) cx_fail(c, t.line, t.col, "float literal is out of range");
            } else {
                t.k = TK_INT;
                errno = 0;
                t.iv = strtoll(buf, NULL, 10);
                if (errno == ERANGE) cx_fail(c, t.line, t.col, "integer literal is out of range");
            }
            tok_push(c, v, t);
            continue;
        }
        if (ch == '"') {
            advance(c);
            size_t cap = 64, n = 0;
            char *buf = malloc(cap);
            if (!buf) cx_fail(c, t.line, t.col, "out of memory while reading source");
            for (;;) {
                int x = cur_char(c);
                if (x == -1 || x == '\n') {
                    free(buf);
                    cx_fail(c, t.line, t.col, "unterminated string");
                }
                advance(c);
                if (x == '"') break;
                if (x == '\\') {
                    int e = cur_char(c);
                    if (e == -1) { free(buf); cx_fail(c, t.line, t.col, "unterminated string"); }
                    advance(c);
                    switch (e) {
                    case 'n': x = '\n'; break;
                    case 't': x = '\t'; break;
                    case 'r': x = '\r'; break;
                    case '"': x = '"'; break;
                    case '\\': x = '\\'; break;
                    default:
                        free(buf);
                        cx_fail(c, c->line, c->col - 1, "unknown escape sequence");
                    }
                }
                if (n + 1 >= cap) {
                    if (cap >= FORGE_MAX_SOURCE) { free(buf); cx_fail(c, t.line, t.col, "string literal is too long"); }
                    cap *= 2;
                    char *nb = realloc(buf, cap);
                    if (!nb) { free(buf); cx_fail(c, t.line, t.col, "out of memory while reading source"); }
                    buf = nb;
                }
                buf[n++] = (char)x;
            }
            t.k = TK_STR;
            t.text = arena_strndup(c->ar, buf, n);
            free(buf);
            if (!t.text) cx_fail(c, t.line, t.col, "out of memory while reading source");
            t.tlen = n;
            tok_push(c, v, t);
            continue;
        }
        static const char *const two[] = {"==", "!=", "<=", ">=", NULL};
        int matched = 0;
        for (size_t i = 0; two[i] && !matched; i++) {
            if (ch == two[i][0] && peek_char(c, 1) == two[i][1]) {
                t.k = TK_OP;
                t.text = (char *)two[i];
                advance(c);
                advance(c);
                matched = 1;
            }
        }
        if (!matched) {
            static const char one[] = "(){}[],:=<>+-*/%";
            if (ch && strchr(one, ch)) {
                t.k = TK_OP;
                char one_char = (char)ch;
                t.text = arena_strndup(c->ar, &one_char, 1);
                if (!t.text) cx_fail(c, t.line, t.col, "out of memory while reading source");
                advance(c);
            } else {
                if (ch >= 0x20 && ch < 0x7f) cx_fail(c, t.line, t.col, "unexpected character '%c'", ch);
                else cx_fail(c, t.line, t.col, "unexpected byte 0x%02X", (unsigned)ch);
            }
        }
        tok_push(c, v, t);
    }
}

/* ---------- parser ---------- */

struct parser {
    struct cx *c;
    token *t;
    size_t n, i;
    int depth;
};

#define FORGE_MAX_NESTING 200

#define NEST_BEGIN(p) do { if (++(p)->depth > FORGE_MAX_NESTING) \
    cx_fail((p)->c, tok(p)->line, tok(p)->col, "code is nested too deeply"); } while (0)
#define NEST_END(p) ((p)->depth--)

static const token *tok(struct parser *p) { return &p->t[p->i]; }

static void tok_describe(const token *t, char *out, size_t size) {
    switch (t->k) {
    case TK_EOF: snprintf(out, size, "end of file"); break;
    case TK_IDENT: case TK_OP: snprintf(out, size, "'%s'", t->text); break;
    case TK_INT: snprintf(out, size, "integer %lld", (long long)t->iv); break;
    case TK_FLT: snprintf(out, size, "float literal"); break;
    case TK_STR: snprintf(out, size, "string literal"); break;
    }
}

static node *node_new(struct parser *p, node_kind k, const token *t) {
    node *n = arena_alloc(p->c->ar, sizeof *n);
    if (!n) cx_fail(p->c, t->line, t->col, "out of memory while parsing");
    n->kind = k;
    n->line = t->line;
    n->col = t->col;
    n->file = p->c->file;
    return n;
}

static int is_op(struct parser *p, const char *s) {
    return tok(p)->k == TK_OP && !strcmp(tok(p)->text, s);
}

static int is_kw(struct parser *p, const char *s) {
    return tok(p)->k == TK_IDENT && !strcmp(tok(p)->text, s);
}

static void advance_tok(struct parser *p) {
    if (p->i + 1 < p->n) p->i++;
}

__attribute__((noreturn)) static void expected(struct parser *p, const char *what) {
    char found[64];
    tok_describe(tok(p), found, sizeof found);
    cx_fail(p->c, tok(p)->line, tok(p)->col, "expected %s but found %s", what, found);
}

static void expect_op(struct parser *p, const char *s) {
    if (!is_op(p, s)) {
        char what[32];
        snprintf(what, sizeof what, "'%s'", s);
        expected(p, what);
    }
    advance_tok(p);
}

static char *expect_name(struct parser *p) {
    if (tok(p)->k != TK_IDENT || is_keyword(tok(p)->text)) expected(p, "a name");
    char *name = tok(p)->text;
    advance_tok(p);
    return name;
}

static node *parse_expr(struct parser *p);
static node *parse_block(struct parser *p);
static node *parse_stmt(struct parser *p);
static node *parse_fn_decl(struct parser *p, node_kind kind);

static node *parse_primary_inner(struct parser *p);

static node *parse_primary(struct parser *p) {
    NEST_BEGIN(p);
    node *n = parse_primary_inner(p);
    NEST_END(p);
    return n;
}

static node *parse_primary_inner(struct parser *p) {
    const token *t = tok(p);
    node *n;
    switch (t->k) {
    case TK_INT: n = node_new(p, N_INT, t); n->ival = t->iv; advance_tok(p); return n;
    case TK_FLT: n = node_new(p, N_FLT, t); n->fval = t->fv; advance_tok(p); return n;
    case TK_STR:
        n = node_new(p, N_STR, t);
        n->name = t->text;
        n->slen = t->tlen;
        advance_tok(p);
        return n;
    case TK_IDENT:
        if (!strcmp(t->text, "true") || !strcmp(t->text, "false")) {
            n = node_new(p, N_BOOL, t);
            n->ival = !strcmp(t->text, "true");
            advance_tok(p);
            return n;
        }
        if (!strcmp(t->text, "nil")) { n = node_new(p, N_NIL, t); advance_tok(p); return n; }
        if (!strcmp(t->text, "fn")) return parse_fn_decl(p, N_LAMBDA);
        if (is_keyword(t->text)) expected(p, "an expression");
        n = node_new(p, N_IDENT, t);
        n->name = t->text;
        advance_tok(p);
        return n;
    case TK_OP:
        if (!strcmp(t->text, "(")) {
            advance_tok(p);
            n = parse_expr(p);
            expect_op(p, ")");
            return n;
        }
        if (!strcmp(t->text, "[")) {
            n = node_new(p, N_LIST, t);
            advance_tok(p);
            while (!is_op(p, "]")) {
                kid_push(p->c->ar, n, parse_expr(p));
                if (!is_op(p, ",")) break;
                advance_tok(p);
            }
            expect_op(p, "]");
            return n;
        }
        if (!strcmp(t->text, "{")) {
            n = node_new(p, N_MAP, t);
            advance_tok(p);
            while (!is_op(p, "}")) {
                node *key = parse_expr(p);
                expect_op(p, ":");
                node *val = parse_expr(p);
                kid_push(p->c->ar, n, key);
                kid_push(p->c->ar, n, val);
                if (!is_op(p, ",")) break;
                advance_tok(p);
            }
            expect_op(p, "}");
            return n;
        }
        break;
    case TK_EOF:
        break;
    }
    expected(p, "an expression");
}

static node *parse_postfix(struct parser *p) {
    node *e = parse_primary(p);
    for (;;) {
        if (is_op(p, "(")) {
            node *call = node_new(p, N_CALL, tok(p));
            call->a = e;
            advance_tok(p);
            while (!is_op(p, ")")) {
                kid_push(p->c->ar, call, parse_expr(p));
                if (!is_op(p, ",")) break;
                advance_tok(p);
            }
            expect_op(p, ")");
            e = call;
        } else if (is_op(p, "[")) {
            node *idx = node_new(p, N_INDEX, tok(p));
            idx->a = e;
            advance_tok(p);
            idx->b = parse_expr(p);
            expect_op(p, "]");
            e = idx;
        } else {
            return e;
        }
    }
}

static node *parse_unary(struct parser *p) {
    if (is_op(p, "-")) {
        NEST_BEGIN(p);
        node *n = node_new(p, N_UNARY, tok(p));
        n->op = OP_NEG;
        advance_tok(p);
        n->a = parse_unary(p);
        NEST_END(p);
        return n;
    }
    return parse_postfix(p);
}

static node *binary(struct parser *p, node *lhs, int op, node *rhs, const token *at) {
    node *n = node_new(p, N_BINARY, at);
    n->op = op;
    n->a = lhs;
    n->b = rhs;
    return n;
}

static node *parse_mul(struct parser *p) {
    node *e = parse_unary(p);
    for (;;) {
        const token *at = tok(p);
        if (is_op(p, "*")) { advance_tok(p); e = binary(p, e, OP_MUL, parse_unary(p), at); }
        else if (is_op(p, "/")) { advance_tok(p); e = binary(p, e, OP_DIV, parse_unary(p), at); }
        else if (is_op(p, "%")) { advance_tok(p); e = binary(p, e, OP_MOD, parse_unary(p), at); }
        else return e;
    }
}

static node *parse_add(struct parser *p) {
    node *e = parse_mul(p);
    for (;;) {
        const token *at = tok(p);
        if (is_op(p, "+")) { advance_tok(p); e = binary(p, e, OP_ADD, parse_mul(p), at); }
        else if (is_op(p, "-")) { advance_tok(p); e = binary(p, e, OP_SUB, parse_mul(p), at); }
        else return e;
    }
}

static node *parse_compare(struct parser *p) {
    node *e = parse_add(p);
    for (;;) {
        const token *at = tok(p);
        if (is_op(p, "<")) { advance_tok(p); e = binary(p, e, OP_LT, parse_add(p), at); }
        else if (is_op(p, "<=")) { advance_tok(p); e = binary(p, e, OP_LE, parse_add(p), at); }
        else if (is_op(p, ">")) { advance_tok(p); e = binary(p, e, OP_GT, parse_add(p), at); }
        else if (is_op(p, ">=")) { advance_tok(p); e = binary(p, e, OP_GE, parse_add(p), at); }
        else return e;
    }
}

static node *parse_equality(struct parser *p) {
    node *e = parse_compare(p);
    for (;;) {
        const token *at = tok(p);
        if (is_op(p, "==")) { advance_tok(p); e = binary(p, e, OP_EQ, parse_compare(p), at); }
        else if (is_op(p, "!=")) { advance_tok(p); e = binary(p, e, OP_NE, parse_compare(p), at); }
        else return e;
    }
}

static node *parse_not(struct parser *p) {
    if (is_kw(p, "not")) {
        NEST_BEGIN(p);
        node *n = node_new(p, N_UNARY, tok(p));
        n->op = OP_NOT;
        advance_tok(p);
        n->a = parse_not(p);
        NEST_END(p);
        return n;
    }
    return parse_equality(p);
}

static node *parse_and(struct parser *p) {
    node *e = parse_not(p);
    while (is_kw(p, "and")) {
        node *n = node_new(p, N_AND, tok(p));
        advance_tok(p);
        n->a = e;
        n->b = parse_not(p);
        e = n;
    }
    return e;
}

static node *parse_expr(struct parser *p) {
    NEST_BEGIN(p);
    node *e = parse_and(p);
    while (is_kw(p, "or")) {
        node *n = node_new(p, N_OR, tok(p));
        advance_tok(p);
        n->a = e;
        n->b = parse_and(p);
        e = n;
    }
    NEST_END(p);
    return e;
}

static node *parse_fn_decl(struct parser *p, node_kind kind) {
    const token *at = tok(p);
    advance_tok(p); /* 'fn' */
    node *fn = node_new(p, kind, at);
    fn->name = kind == N_LAMBDA ? "lambda" : expect_name(p);
    expect_op(p, "(");
    while (!is_op(p, ")")) {
        char *param = expect_name(p);
        for (size_t i = 0; i < fn->nparams; i++) {
            if (!strcmp(fn->params[i], param)) {
                cx_fail(p->c, tok(p)->line, tok(p)->col, "duplicate parameter '%s'", param);
            }
        }
        char **np = arena_alloc(p->c->ar, (fn->nparams + 1) * sizeof *np);
        if (!np) cx_fail(p->c, at->line, at->col, "out of memory while parsing");
        if (fn->nparams) memcpy(np, fn->params, fn->nparams * sizeof *np);
        np[fn->nparams++] = param;
        fn->params = np;
        if (!is_op(p, ",")) break;
        advance_tok(p);
    }
    expect_op(p, ")");
    fn->b = parse_block(p);
    return fn;
}

static node *parse_block(struct parser *p) {
    node *blk = node_new(p, N_BLOCK, tok(p));
    expect_op(p, "{");
    while (!is_op(p, "}")) {
        if (tok(p)->k == TK_EOF) expected(p, "'}'");
        kid_push(p->c->ar, blk, parse_stmt(p));
    }
    advance_tok(p);
    return blk;
}

static node *parse_if(struct parser *p) {
    node *n = node_new(p, N_IF, tok(p));
    advance_tok(p); /* 'if' */
    n->a = parse_expr(p);
    n->b = parse_block(p);
    if (is_kw(p, "else")) {
        advance_tok(p);
        if (is_kw(p, "if")) n->c = parse_if(p);
        else n->c = parse_block(p);
    }
    return n;
}

static node *parse_stmt_inner(struct parser *p);

static node *parse_stmt(struct parser *p) {
    NEST_BEGIN(p);
    node *n = parse_stmt_inner(p);
    NEST_END(p);
    return n;
}

static node *parse_stmt_inner(struct parser *p) {
    const token *t = tok(p);
    node *n;
    if (t->k == TK_IDENT) {
        if (!strcmp(t->text, "let")) {
            n = node_new(p, N_LET, t);
            advance_tok(p);
            n->name = expect_name(p);
            expect_op(p, "=");
            n->a = parse_expr(p);
            return n;
        }
        if (!strcmp(t->text, "fn")) return parse_fn_decl(p, N_FN);
        if (!strcmp(t->text, "if")) return parse_if(p);
        if (!strcmp(t->text, "while")) {
            n = node_new(p, N_WHILE, t);
            advance_tok(p);
            n->a = parse_expr(p);
            n->b = parse_block(p);
            return n;
        }
        if (!strcmp(t->text, "for")) {
            n = node_new(p, N_FOR, t);
            advance_tok(p);
            n->name = expect_name(p);
            if (!is_kw(p, "in")) expected(p, "'in'");
            advance_tok(p);
            n->a = parse_expr(p);
            n->b = parse_block(p);
            return n;
        }
        if (!strcmp(t->text, "return")) {
            n = node_new(p, N_RETURN, t);
            advance_tok(p);
            /* A return value must start on the same line; otherwise the next
               statement would be swallowed as the value. */
            if (!is_op(p, "}") && tok(p)->k != TK_EOF && tok(p)->line == t->line) n->a = parse_expr(p);
            return n;
        }
        if (!strcmp(t->text, "break")) { advance_tok(p); return node_new(p, N_BREAK, t); }
        if (!strcmp(t->text, "continue")) { advance_tok(p); return node_new(p, N_CONTINUE, t); }
        if (!strcmp(t->text, "import")) cx_fail(p->c, t->line, t->col, "import is only allowed at the top level");
    }
    if (is_op(p, "{")) return parse_block(p);

    node *e = parse_expr(p);
    if (is_op(p, "=")) {
        if (e->kind != N_IDENT && e->kind != N_INDEX)
            cx_fail(p->c, e->line, e->col, "invalid assignment target");
        n = node_new(p, N_ASSIGN, tok(p));
        advance_tok(p);
        n->a = e;
        n->b = parse_expr(p);
        n->line = e->line;
        n->col = e->col;
        return n;
    }
    n = node_new(p, N_EXPR, t);
    n->line = e->line;
    n->col = e->col;
    n->a = e;
    return n;
}

static node *parse_top(struct parser *p, struct cx *c) {
    node *root = arena_alloc(c->ar, sizeof *root);
    if (!root) cx_fail(c, 1, 1, "out of memory while parsing");
    root->kind = N_BLOCK;
    root->file = c->file;
    while (tok(p)->k != TK_EOF) {
        const token *t = tok(p);
        if (is_kw(p, "import")) {
            node *imp = node_new(p, N_IMPORT, t);
            advance_tok(p);
            if (tok(p)->k != TK_STR) expected(p, "a file name in quotes");
            imp->name = tok(p)->text;
            imp->slen = tok(p)->tlen;
            advance_tok(p);
            kid_push(c->ar, root, imp);
        } else if (is_kw(p, "fn")) {
            kid_push(c->ar, root, parse_fn_decl(p, N_FN));
        } else if (is_kw(p, "let")) {
            kid_push(c->ar, root, parse_stmt(p));
        } else {
            cx_fail(c, t->line, t->col, "only let, fn and import may appear at the top level");
        }
    }
    return root;
}

/* ---------- loading and imports ---------- */

static int read_source(const char *path, char **out, size_t *len, char *err, size_t err_size) {
    FILE *f = fopen(path, "rb");
    if (!f) { snprintf(err, err_size, "cannot read file"); return -1; }
    struct stat st;
    if (fstat(fileno(f), &st) || !S_ISREG(st.st_mode)) {
        fclose(f);
        snprintf(err, err_size, "not a regular file");
        return -1;
    }
    if ((size_t)st.st_size > FORGE_MAX_SOURCE) {
        fclose(f);
        snprintf(err, err_size, "source file is larger than 1 MiB");
        return -1;
    }
    char *buf = malloc((size_t)st.st_size + 1);
    if (!buf) { fclose(f); snprintf(err, err_size, "out of memory"); return -1; }
    size_t n = fread(buf, 1, (size_t)st.st_size, f);
    fclose(f);
    buf[n] = '\0';
    *out = buf;
    *len = n;
    return 0;
}

static void add_diag(struct forge_diags *d, const char *file, int line, int col, const char *msg) {
    if (!d || d->n >= FORGE_MAX_DIAGS) return;
    struct forge_diag *x = &d->d[d->n++];
    snprintf(x->file, sizeof x->file, "%s", file ? file : "");
    x->line = line;
    x->col = col;
    snprintf(x->msg, sizeof x->msg, "%s", msg);
}

struct loader {
    forge_program *prog;
    struct forge_diags *diags;
    char *realpaths[FORGE_MAX_FILES];
    int state[FORGE_MAX_FILES]; /* 1 loading, 2 done */
    size_t nreal;
    node *merged[FORGE_MAX_FILES * 8];
    size_t nmerged;
    int failed;
};

static int load_one(struct loader *L, const char *path, const char *display, const char *from, int line, int col);

static const char *prog_display_of(struct loader *L, int file_index) {
    return L->prog->files.path[file_index];
}

static int find_real(struct loader *L, const char *rp) {
    for (size_t i = 0; i < L->nreal; i++) if (!strcmp(L->realpaths[i], rp)) return (int)i;
    return -1;
}

/* from/line/col locate the import that asked for this file, so load errors point at it. */
static int load_one(struct loader *L, const char *path, const char *display, const char *from, int line, int col) {
    char *rp = realpath(path, NULL);
    if (!rp) {
        add_diag(L->diags, from, line, col, "file not found");
        L->failed = 1;
        return -1;
    }
    int idx = find_real(L, rp);
    if (idx >= 0) {
        free(rp);
        if (L->state[idx] == 1) {
            add_diag(L->diags, from, line, col, "import cycle");
            L->failed = 1;
            return -1;
        }
        return 0;
    }
    if (L->nreal >= FORGE_MAX_FILES) {
        free(rp);
        add_diag(L->diags, from, line, col, "too many source files");
        L->failed = 1;
        return -1;
    }
    idx = (int)L->nreal;
    L->realpaths[L->nreal++] = rp;
    L->state[idx] = 1;

    char *text;
    size_t len;
    char err[128];
    if (read_source(rp, &text, &len, err, sizeof err)) {
        add_diag(L->diags, from, line, col, err);
        L->failed = 1;
        return -1;
    }

    forge_program *prog = L->prog;
    int file_index = (int)prog->files.n;
    if (prog->files.n >= FORGE_MAX_FILES) {
        free(text);
        add_diag(L->diags, from, line, col, "too many source files");
        L->failed = 1;
        return -1;
    }
    prog->files.path[prog->files.n++] = arena_strndup(&prog->ar, display, strlen(display));

    struct cx c;
    memset(&c, 0, sizeof c);
    c.ar = &prog->ar;
    c.src = text;
    c.n = len;
    c.file = file_index;
    jmp_buf jb;
    c.jb = &jb;
    struct tokvec tv = {0};
    struct parser ps;
    node *root = NULL;
    if (setjmp(jb) == 0) {
        lex(&c, &tv);
        memset(&ps, 0, sizeof ps);
        ps.c = &c;
        ps.t = tv.t;
        ps.n = tv.n;
        ps.i = 0;
        root = parse_top(&ps, &c);
    } else {
        add_diag(L->diags, display, c.eline, c.ecol, c.msg);
        free(tv.t);
        free(text);
        L->failed = 1;
        return -1;
    }
    free(tv.t);
    free(text);

    /* Imports load first, so their declarations come before this file's. */
    for (size_t i = 0; i < root->nkids; i++) {
        node *k = root->kids[i];
        if (k->kind != N_IMPORT) continue;
        const char *rel = k->name;
        if (rel[0] == '/' || strstr(rel, "..") || strchr(rel, '\\') || rel[0] == '\0') {
            add_diag(L->diags, prog->files.path[file_index], k->line, k->col, "import path must be relative and inside the project");
            L->failed = 1;
            continue;
        }
        char dir[PATH_MAX], target[PATH_MAX];
        snprintf(dir, sizeof dir, "%s", rp);
        char *slash = strrchr(dir, '/');
        if (slash) *slash = '\0';
        if (strlen(dir) + strlen(rel) + 2 > sizeof target) {
            add_diag(L->diags, prog_display_of(L, file_index), k->line, k->col, "import path is too long");
            L->failed = 1;
            continue;
        }
        size_t dl = strlen(dir), rl = strlen(rel);
        memcpy(target, dir, dl);
        target[dl] = '/';
        memcpy(target + dl + 1, rel, rl + 1);
        char shown[256];
        const char *slash_at = strrchr(display, '/');
        size_t prefix = slash_at ? (size_t)(slash_at - display) + 1 : 0;
        if (prefix >= sizeof shown) prefix = 0;
        snprintf(shown, sizeof shown, "%.*s%s", (int)prefix, display, rel);
        if (load_one(L, target, shown, display, k->line, k->col)) {
            /* load_one already reported the problem */
        }
    }
    for (size_t i = 0; i < root->nkids; i++) {
        node *k = root->kids[i];
        if (k->kind == N_IMPORT) continue;
        if (L->nmerged < sizeof L->merged / sizeof L->merged[0]) L->merged[L->nmerged++] = k;
        else { add_diag(L->diags, display, k->line, k->col, "program is too large"); L->failed = 1; }
    }
    L->state[idx] = 2;
    return L->failed ? -1 : 0;
}

/* ---------- static checker ---------- */

struct rscope {
    const char **names;
    size_t n, cap;
};

struct resolver {
    forge_program *prog;
    struct forge_diags *diags;
    struct rscope scopes[256];
    size_t depth;
    const char *globals[FORGE_MAX_DIAGS * 16];
    node *global_nodes[FORGE_MAX_DIAGS * 16]; /* the declaration behind each global name */
    size_t nglobals;
    int in_fn;
    int loops;
    int file;
};

/* One list defines every builtin: name, implementation, minimum and maximum
   argument count (-1 means no maximum). The checker and the interpreter both
   read this list, so they cannot disagree. */
#define FORGE_BUILTINS(X) \
    X("print", bi_print, 0, -1) X("len", bi_len, 1, 1) X("str", bi_str, 1, 1) \
    X("int", bi_int, 1, 1) X("float", bi_float, 1, 1) X("type", bi_type, 1, 1) \
    X("push", bi_push, 2, 2) X("pop", bi_pop, 1, 1) X("keys", bi_keys, 1, 1) \
    X("has", bi_has, 2, 2) X("remove", bi_remove, 2, 2) \
    X("split", bi_split, 2, 2) X("join", bi_join, 2, 2) X("upper", bi_upper, 1, 1) \
    X("lower", bi_lower, 1, 1) X("trim", bi_trim, 1, 1) X("contains", bi_contains, 2, 2) \
    X("starts_with", bi_starts_with, 2, 2) X("ends_with", bi_ends_with, 2, 2) \
    X("replace", bi_replace, 3, 3) X("substr", bi_substr, 3, 3) X("abs", bi_abs, 1, 1) \
    X("min", bi_min, 2, 2) X("max", bi_max, 2, 2) X("floor", bi_floor, 1, 1) \
    X("sqrt", bi_sqrt, 1, 1) X("range", bi_range, 1, 1) X("exit", bi_exit, 1, 1) \
    X("assert", bi_assert, 1, 2) X("read_asset", bi_read_asset, 1, 1) X("error", bi_error, 1, 1)

struct builtin_arity { const char *name; int min, max; };
#define X_ARITY(nm, fn, lo, hi) { nm, lo, hi },
static const struct builtin_arity arities[] = { FORGE_BUILTINS(X_ARITY) { NULL, 0, 0 } };

static int builtin_index(const char *name) {
    for (size_t i = 0; arities[i].name; i++) if (!strcmp(arities[i].name, name)) return (int)i;
    return -1;
}

static int is_builtin(const char *name) { return builtin_index(name) >= 0; }

static void res_diag(struct resolver *r, const node *n, const char *fmt, ...) {
    char msg[FORGE_MSG_MAX];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    add_diag(r->diags, r->prog->files.path[n->file], n->line, n->col, msg);
}

static int scope_has(const struct rscope *s, const char *name) {
    for (size_t i = 0; i < s->n; i++) if (!strcmp(s->names[i], name)) return 1;
    return 0;
}

static int global_has(const struct resolver *r, const char *name) {
    for (size_t i = 0; i < r->nglobals; i++) if (!strcmp(r->globals[i], name)) return 1;
    return 0;
}

static int local_has(const struct resolver *r, const char *name) {
    for (size_t i = r->depth; i-- > 0;) if (scope_has(&r->scopes[i], name)) return 1;
    return 0;
}

static node *global_decl(const struct resolver *r, const char *name) {
    for (size_t i = 0; i < r->nglobals; i++) if (!strcmp(r->globals[i], name)) return r->global_nodes[i];
    return NULL;
}

static int name_visible(const struct resolver *r, const char *name) {
    for (size_t i = r->depth; i-- > 0;) if (scope_has(&r->scopes[i], name)) return 1;
    return global_has(r, name);
}

/* Declares a name in the innermost scope. Returns 0 on success, -1 if already there. */
static int declare(struct resolver *r, const char *name) {
    struct rscope *s = r->depth ? &r->scopes[r->depth - 1] : NULL;
    if (!s) return -1;
    if (scope_has(s, name)) return -1;
    if (s->n == s->cap) {
        size_t nc = s->cap ? s->cap * 2 : 8;
        const char **nn = realloc((void *)s->names, nc * sizeof *nn);
        if (!nn) return -1;
        s->names = nn;
        s->cap = nc;
    }
    s->names[s->n++] = name;
    return 0;
}

/* Parser nesting is capped at FORGE_MAX_NESTING, below the scope array size,
   so this cannot overflow for parsed programs. */
static void push_scope(struct resolver *r, const node *at) {
    (void)at;
    if (r->depth >= sizeof r->scopes / sizeof r->scopes[0]) abort();
    memset(&r->scopes[r->depth], 0, sizeof r->scopes[0]);
    r->depth++;
}

static void pop_scope(struct resolver *r) {
    if (r->depth) {
        free((void *)r->scopes[r->depth - 1].names);
        r->depth--;
    }
}

static void resolve_expr(struct resolver *r, node *n);
static void resolve_stmt(struct resolver *r, node *n);

static void resolve_block_body(struct resolver *r, node *blk) {
    push_scope(r, blk);
    /* Functions are visible across the whole block, as at run time. */
    for (size_t i = 0; i < blk->nkids; i++) {
        node *k = blk->kids[i];
        if (k->kind == N_FN && declare(r, k->name)) res_diag(r, k, "'%s' is already declared in this scope", k->name);
    }
    for (size_t i = 0; i < blk->nkids; i++) resolve_stmt(r, blk->kids[i]);
    pop_scope(r);
}

static void resolve_fn(struct resolver *r, node *fn) {
    int saved_in_fn = r->in_fn, saved_loops = r->loops;
    size_t saved_depth = r->depth;
    /* A function body sees globals and its own parameters, not the caller's locals. */
    r->in_fn = 1;
    r->loops = 0;
    size_t hidden = r->depth;
    (void)hidden;
    push_scope(r, fn);
    for (size_t i = 0; i < fn->nparams; i++) {
        if (declare(r, fn->params[i])) res_diag(r, fn, "duplicate parameter '%s'", fn->params[i]);
    }
    resolve_block_body(r, fn->b);
    while (r->depth > saved_depth) pop_scope(r);
    r->in_fn = saved_in_fn;
    r->loops = saved_loops;
}

static void resolve_call(struct resolver *r, node *n) {
    if (n->a->kind == N_IDENT && !local_has(r, n->a->name)) {
        node *decl = global_decl(r, n->a->name);
        if (decl && decl->kind == N_FN && decl->nparams != n->nkids)
            res_diag(r, n, "%s expects %zu argument%s, got %zu", decl->name, decl->nparams,
                     decl->nparams == 1 ? "" : "s", n->nkids);
    }
    if (n->a->kind == N_IDENT && !name_visible(r, n->a->name) && is_builtin(n->a->name)) {
        for (size_t i = 0; arities[i].name; i++) {
            if (strcmp(arities[i].name, n->a->name)) continue;
            size_t got = n->nkids;
            if ((int)got < arities[i].min || (arities[i].max >= 0 && (int)got > arities[i].max)) {
                if (arities[i].max < 0)
                    res_diag(r, n, "%s expects at least %d argument%s", arities[i].name, arities[i].min, arities[i].min == 1 ? "" : "s");
                else if (arities[i].min == arities[i].max)
                    res_diag(r, n, "%s expects %d argument%s, got %zu", arities[i].name, arities[i].min, arities[i].min == 1 ? "" : "s", got);
                else
                    res_diag(r, n, "%s expects %d to %d arguments, got %zu", arities[i].name, arities[i].min, arities[i].max, got);
            }
        }
    } else {
        resolve_expr(r, n->a);
    }
    for (size_t i = 0; i < n->nkids; i++) resolve_expr(r, n->kids[i]);
}

static void resolve_expr(struct resolver *r, node *n) {
    switch (n->kind) {
    case N_INT: case N_FLT: case N_STR: case N_BOOL: case N_NIL:
        return;
    case N_IDENT:
        if (!name_visible(r, n->name) && !is_builtin(n->name)) res_diag(r, n, "undefined name '%s'", n->name);
        return;
    case N_LIST:
    case N_MAP:
        for (size_t i = 0; i < n->nkids; i++) resolve_expr(r, n->kids[i]);
        return;
    case N_LAMBDA:
        resolve_fn(r, n);
        return;
    case N_UNARY:
        resolve_expr(r, n->a);
        return;
    case N_BINARY: case N_AND: case N_OR:
        resolve_expr(r, n->a);
        resolve_expr(r, n->b);
        return;
    case N_CALL:
        resolve_call(r, n);
        return;
    case N_INDEX:
        resolve_expr(r, n->a);
        resolve_expr(r, n->b);
        return;
    default:
        res_diag(r, n, "internal error: unexpected expression");
        return;
    }
}

static void resolve_stmt(struct resolver *r, node *n) {
    switch (n->kind) {
    case N_LET:
        resolve_expr(r, n->a);
        if (declare(r, n->name)) res_diag(r, n, "'%s' is already declared in this scope", n->name);
        return;
    case N_FN:
        resolve_fn(r, n);
        return;
    case N_ASSIGN:
        if (n->a->kind == N_IDENT) {
            if (!name_visible(r, n->a->name)) res_diag(r, n, "assignment to undeclared name '%s'", n->a->name);
        } else {
            resolve_expr(r, n->a);
        }
        resolve_expr(r, n->b);
        return;
    case N_IF:
        resolve_expr(r, n->a);
        resolve_block_body(r, n->b);
        if (n->c) {
            if (n->c->kind == N_IF) resolve_stmt(r, n->c);
            else resolve_block_body(r, n->c);
        }
        return;
    case N_WHILE:
        resolve_expr(r, n->a);
        r->loops++;
        resolve_block_body(r, n->b);
        r->loops--;
        return;
    case N_FOR:
        resolve_expr(r, n->a);
        push_scope(r, n);
        if (declare(r, n->name)) res_diag(r, n, "'%s' is already declared in this scope", n->name);
        r->loops++;
        resolve_block_body(r, n->b);
        r->loops--;
        pop_scope(r);
        return;
    case N_RETURN:
        if (!r->in_fn) res_diag(r, n, "return outside a function");
        if (n->a) resolve_expr(r, n->a);
        return;
    case N_BREAK:
        if (!r->loops) res_diag(r, n, "break outside a loop");
        return;
    case N_CONTINUE:
        if (!r->loops) res_diag(r, n, "continue outside a loop");
        return;
    case N_EXPR:
        resolve_expr(r, n->a);
        return;
    case N_BLOCK:
        resolve_block_body(r, n);
        return;
    default:
        res_diag(r, n, "internal error: unexpected statement");
        return;
    }
}

static void check_program(forge_program *p, struct forge_diags *diags, struct loader *L) {
    struct resolver r;
    memset(&r, 0, sizeof r);
    r.prog = p;
    r.diags = diags;
    /* Top-level names from every file share one namespace. */
    for (size_t i = 0; i < L->nmerged; i++) {
        node *k = L->merged[i];
        if (k->kind != N_LET && k->kind != N_FN) continue;
        if (r.nglobals >= sizeof r.globals / sizeof r.globals[0]) break;
        if (global_has(&r, k->name)) {
            res_diag(&r, k, "'%s' is already defined", k->name);
            continue;
        }
        if (is_builtin(k->name)) {
            res_diag(&r, k, "'%s' is a builtin name and cannot be redefined", k->name);
            continue;
        }
        r.global_nodes[r.nglobals] = k;
        r.globals[r.nglobals++] = k->name;
    }
    for (size_t i = 0; i < L->nmerged; i++) {
        node *k = L->merged[i];
        if (k->kind == N_FN) resolve_fn(&r, k);
        else if (k->kind == N_LET) {
            resolve_expr(&r, k->a);
        }
    }
}

/* Returns 0 with the program filled in, or -1 with diagnostics. */
int forge_load(const char *entry, forge_program **out, struct forge_diags *diags) {
    *out = NULL;
    if (diags) diags->n = 0;
    forge_program *dummy = calloc(1, sizeof *dummy);
    if (!dummy) { add_diag(diags, entry, 0, 0, "out of memory"); return -1; }

    struct loader L;
    memset(&L, 0, sizeof L);
    L.prog = dummy;
    L.diags = diags;
    const char *shown_entry = strrchr(entry, '/');
    shown_entry = shown_entry ? shown_entry + 1 : entry;
    if (load_one(&L, entry, shown_entry, shown_entry, 0, 0) || L.failed) {
        for (size_t i = 0; i < L.nreal; i++) free(L.realpaths[i]);
        arena_free(&dummy->ar);
        free(dummy);
        return -1;
    }
    for (size_t i = 0; i < L.nreal; i++) free(L.realpaths[i]);

    /* Build the merged root now that every file is parsed. */
    node *root = arena_alloc(&dummy->ar, sizeof *root);
    if (!root) { arena_free(&dummy->ar); free(dummy); add_diag(diags, entry, 0, 0, "out of memory"); return -1; }
    root->kind = N_BLOCK;
    for (size_t i = 0; i < L.nmerged; i++) kid_push(&dummy->ar, root, L.merged[i]);
    dummy->root = root;

    check_program(dummy, diags, &L);
    if (diags->n) {
        arena_free(&dummy->ar);
        free(dummy);
        return -1;
    }
    *out = dummy;
    return 0;
}

void forge_free(forge_program *p) {
    if (!p) return;
    arena_free(&p->ar);
    free(p);
}

int forge_has_function(const forge_program *p, const char *name) {
    if (!p || !p->root) return 0;
    for (size_t i = 0; i < p->root->nkids; i++) {
        node *k = p->root->kids[i];
        if (k->kind == N_FN && !strcmp(k->name, name)) return 1;
    }
    return 0;
}

/* ---------- runtime values ---------- */

typedef enum { V_NIL, V_BOOL, V_INT, V_FLT, V_STR, V_LIST, V_MAP, V_FN, V_BUILTIN } vkind;

typedef struct value value;
typedef struct str { size_t len; char data[]; } str;
struct value {
    vkind k;
    union {
        int b;
        int64_t i;
        double f;
        str *s;
        struct list *l;
        struct map *m;
        struct closure *fn;
        int bi;
    } u;
};
struct list { value *items; size_t n, cap; };
struct mentry { str *key; value v; };
struct map { struct mentry *e; size_t n, cap; };
struct closure { node *decl; struct env *env; };
struct binding { const char *name; value v; };
struct env { struct env *parent; struct binding *vars; size_t n, cap; };


struct ctx {
    struct arena heap;
    FILE *out, *err;
    const char *assets;
    jmp_buf *jb;
    int jb_code;      /* 1 runtime error, 2 exit() */
    int exit_code;
    char msg[FORGE_MSG_MAX];
    forge_program *prog;
    node *cur;
    int depth;
    value ret;
    size_t out_bytes;
    struct env *globals;
};

typedef enum { F_NORMAL, F_BREAK, F_CONTINUE, F_RETURN } flow;

static void rt_fail(struct ctx *c, const char *fmt, ...) __attribute__((noreturn));

static void rt_fail(struct ctx *c, const char *fmt, ...) {
    char text[FORGE_MSG_MAX];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(text, sizeof text, fmt, ap);
    va_end(ap);
    if (c->cur && c->prog && c->cur->file >= 0 && (size_t)c->cur->file < c->prog->files.n) {
        snprintf(c->msg, sizeof c->msg, "%.200s:%d:%d: runtime error: %.280s",
                 c->prog->files.path[c->cur->file], c->cur->line, c->cur->col, text);
    } else {
        snprintf(c->msg, sizeof c->msg, "runtime error: %.400s", text);
    }
    c->jb_code = 1;
    longjmp(*c->jb, 1);
}

static void *ralloc(struct ctx *c, size_t n) {
    void *p = arena_alloc(&c->heap, n);
    if (!p) rt_fail(c, "out of memory (the program may use at most 256 MiB)");
    return p;
}

static value vnil(void) { value v; memset(&v, 0, sizeof v); v.k = V_NIL; return v; }
static value vbool(int b) { value v = vnil(); v.k = V_BOOL; v.u.b = b != 0; return v; }
static value vint(int64_t i) { value v = vnil(); v.k = V_INT; v.u.i = i; return v; }
static value vflt(double f) { value v = vnil(); v.k = V_FLT; v.u.f = f; return v; }
static value vstrv(str *s) { value v = vnil(); v.k = V_STR; v.u.s = s; return v; }

static str *str_new(struct ctx *c, const char *s, size_t n) {
    str *r = ralloc(c, sizeof *r + n + 1);
    r->len = n;
    if (n) memcpy(r->data, s, n);
    r->data[n] = '\0';
    return r;
}

static value vstr_of(struct ctx *c, const char *s, size_t n) { return vstrv(str_new(c, s, n)); }

static struct list *list_new(struct ctx *c) { return ralloc(c, sizeof(struct list)); }

static void list_push(struct ctx *c, struct list *l, value v) {
    if (l->n == l->cap) {
        size_t nc = l->cap ? l->cap * 2 : 8;
        value *ni = ralloc(c, nc * sizeof *ni);
        if (l->n) memcpy(ni, l->items, l->n * sizeof *ni);
        l->items = ni;
        l->cap = nc;
    }
    l->items[l->n++] = v;
}

static struct map *map_new(struct ctx *c) { return ralloc(c, sizeof(struct map)); }

static int str_eq(const str *a, const str *b) { return a->len == b->len && !memcmp(a->data, b->data, a->len); }

static struct mentry *map_find(const struct map *m, const str *key) {
    for (size_t i = 0; i < m->n; i++) if (str_eq(m->e[i].key, key)) return &m->e[i];
    return NULL;
}

static void map_set(struct ctx *c, struct map *m, str *key, value v) {
    struct mentry *e = map_find(m, key);
    if (e) { e->v = v; return; }
    if (m->n == m->cap) {
        size_t nc = m->cap ? m->cap * 2 : 8;
        struct mentry *ne = ralloc(c, nc * sizeof *ne);
        if (m->n) memcpy(ne, m->e, m->n * sizeof *ne);
        m->e = ne;
        m->cap = nc;
    }
    m->e[m->n].key = key;
    m->e[m->n].v = v;
    m->n++;
}

static const char *type_name(const value *v) {
    switch (v->k) {
    case V_NIL: return "nil";
    case V_BOOL: return "bool";
    case V_INT: return "int";
    case V_FLT: return "float";
    case V_STR: return "str";
    case V_LIST: return "list";
    case V_MAP: return "map";
    case V_FN: return "fn";
    case V_BUILTIN: return "builtin";
    }
    return "?";
}

/* ---------- environments ---------- */

static struct env *env_new(struct ctx *c, struct env *parent) {
    struct env *e = ralloc(c, sizeof *e);
    e->parent = parent;
    return e;
}

static value *env_find(struct env *e, const char *name) {
    for (; e; e = e->parent) {
        for (size_t i = 0; i < e->n; i++) if (!strcmp(e->vars[i].name, name)) return &e->vars[i].v;
    }
    return NULL;
}

static void env_define(struct ctx *c, struct env *e, const char *name, value v) {
    for (size_t i = 0; i < e->n; i++) {
        if (!strcmp(e->vars[i].name, name)) rt_fail(c, "'%s' is already declared in this scope", name);
    }
    if (e->n == e->cap) {
        size_t nc = e->cap ? e->cap * 2 : 8;
        struct binding *nb = ralloc(c, nc * sizeof *nb);
        if (e->n) memcpy(nb, e->vars, e->n * sizeof *nb);
        e->vars = nb;
        e->cap = nc;
    }
    e->vars[e->n].name = name;
    e->vars[e->n].v = v;
    e->n++;
}

/* ---------- output and display ---------- */

struct sbuf { char *p; size_t n, cap; };

static void sb_add(struct ctx *c, struct sbuf *b, const char *s, size_t n) {
    if (b->n + n + 1 > b->cap) {
        size_t nc = b->cap ? b->cap : 64;
        while (b->n + n + 1 > nc) nc *= 2;
        char *np = ralloc(c, nc);
        if (b->n) memcpy(np, b->p, b->n);
        b->p = np;
        b->cap = nc;
    }
    if (n) memcpy(b->p + b->n, s, n);
    b->n += n;
    b->p[b->n] = '\0';
}

static void sb_add_str(struct ctx *c, struct sbuf *b, const char *s) { sb_add(c, b, s, strlen(s)); }

static void display_into(struct ctx *c, struct sbuf *b, const value *v, int quote, int depth);

static void display_quoted(struct ctx *c, struct sbuf *b, const str *s) {
    sb_add_str(c, b, "\"");
    for (size_t i = 0; i < s->len; i++) {
        char ch = s->data[i];
        if (ch == '"') sb_add_str(c, b, "\\\"");
        else if (ch == '\\') sb_add_str(c, b, "\\\\");
        else if (ch == '\n') sb_add_str(c, b, "\\n");
        else if (ch == '\t') sb_add_str(c, b, "\\t");
        else if (ch == '\r') sb_add_str(c, b, "\\r");
        else sb_add(c, b, &ch, 1);
    }
    sb_add_str(c, b, "\"");
}

static void display_into(struct ctx *c, struct sbuf *b, const value *v, int quote, int depth) {
    char tmp[64];
    if (depth > 32) { sb_add_str(c, b, "..."); return; }
    switch (v->k) {
    case V_NIL: sb_add_str(c, b, "nil"); return;
    case V_BOOL: sb_add_str(c, b, v->u.b ? "true" : "false"); return;
    case V_INT:
        snprintf(tmp, sizeof tmp, "%lld", (long long)v->u.i);
        sb_add_str(c, b, tmp);
        return;
    case V_FLT: {
        snprintf(tmp, sizeof tmp, "%.15g", v->u.f);
        if (!strpbrk(tmp, ".en")) strncat(tmp, ".0", sizeof tmp - strlen(tmp) - 1);
        sb_add_str(c, b, tmp);
        return;
    }
    case V_STR:
        if (quote) display_quoted(c, b, v->u.s);
        else sb_add(c, b, v->u.s->data, v->u.s->len);
        return;
    case V_LIST:
        sb_add_str(c, b, "[");
        for (size_t i = 0; i < v->u.l->n; i++) {
            if (i) sb_add_str(c, b, ", ");
            display_into(c, b, &v->u.l->items[i], 1, depth + 1);
        }
        sb_add_str(c, b, "]");
        return;
    case V_MAP:
        sb_add_str(c, b, "{");
        for (size_t i = 0; i < v->u.m->n; i++) {
            if (i) sb_add_str(c, b, ", ");
            display_quoted(c, b, v->u.m->e[i].key);
            sb_add_str(c, b, ": ");
            display_into(c, b, &v->u.m->e[i].v, 1, depth + 1);
        }
        sb_add_str(c, b, "}");
        return;
    case V_FN:
        sb_add_str(c, b, "<fn ");
        sb_add_str(c, b, v->u.fn->decl->name);
        sb_add_str(c, b, ">");
        return;
    case V_BUILTIN:
        sb_add_str(c, b, "<builtin ");
        sb_add_str(c, b, arities[v->u.bi].name);
        sb_add_str(c, b, ">");
        return;
    }
}

static str *display_str(struct ctx *c, const value *v, int quote) {
    struct sbuf b = {0};
    display_into(c, &b, v, quote, 0);
    if (!b.p) return str_new(c, "", 0);
    return str_new(c, b.p, b.n);
}

static void out_write(struct ctx *c, const char *s, size_t n) {
    c->out_bytes += n;
    if (c->out_bytes > FORGE_MAX_OUTPUT) rt_fail(c, "program printed more than 16 MiB");
    fwrite(s, 1, n, c->out);
}

/* ---------- operators ---------- */

/* Lists compare element by element and maps compare key by key (order does not matter).
   Functions and builtins compare by identity. Cyclic data stops at a fixed depth and counts as unequal. */
#define EQ_MAX_DEPTH 64
static int values_equal_at(const value *a, const value *b, int depth) {
    if ((a->k == V_INT || a->k == V_FLT) && (b->k == V_INT || b->k == V_FLT)) {
        if (a->k == V_INT && b->k == V_INT) return a->u.i == b->u.i;
        double x = a->k == V_INT ? (double)a->u.i : a->u.f;
        double y = b->k == V_INT ? (double)b->u.i : b->u.f;
        return x == y;
    }
    if (a->k != b->k) return 0;
    switch (a->k) {
    case V_NIL: return 1;
    case V_BOOL: return a->u.b == b->u.b;
    case V_STR: return str_eq(a->u.s, b->u.s);
    case V_LIST: {
        if (a->u.l == b->u.l) return 1;
        if (depth >= EQ_MAX_DEPTH) return 0;
        if (a->u.l->n != b->u.l->n) return 0;
        for (size_t i = 0; i < a->u.l->n; i++)
            if (!values_equal_at(&a->u.l->items[i], &b->u.l->items[i], depth + 1)) return 0;
        return 1;
    }
    case V_MAP: {
        if (a->u.m == b->u.m) return 1;
        if (depth >= EQ_MAX_DEPTH) return 0;
        if (a->u.m->n != b->u.m->n) return 0;
        for (size_t i = 0; i < a->u.m->n; i++) {
            const struct mentry *other = map_find(b->u.m, a->u.m->e[i].key);
            if (!other || !values_equal_at(&a->u.m->e[i].v, &other->v, depth + 1)) return 0;
        }
        return 1;
    }
    case V_FN: return a->u.fn == b->u.fn;
    case V_BUILTIN: return a->u.bi == b->u.bi;
    default: return 0;
    }
}

static int values_equal(const value *a, const value *b) { return values_equal_at(a, b, 0); }

static int is_num(const value *v) { return v->k == V_INT || v->k == V_FLT; }
static double as_dbl(const value *v) { return v->k == V_INT ? (double)v->u.i : v->u.f; }

static int compare_values(struct ctx *c, const value *a, const value *b, int *out) {
    if (a->k == V_INT && b->k == V_INT) { *out = (a->u.i > b->u.i) - (a->u.i < b->u.i); return 1; }
    if (is_num(a) && is_num(b)) {
        double x = as_dbl(a), y = as_dbl(b);
        *out = (x > y) - (x < y);
        return 1;
    }
    if (a->k == V_STR && b->k == V_STR) {
        size_t n = a->u.s->len < b->u.s->len ? a->u.s->len : b->u.s->len;
        int r = memcmp(a->u.s->data, b->u.s->data, n);
        if (!r) r = (a->u.s->len > b->u.s->len) - (a->u.s->len < b->u.s->len);
        *out = (r > 0) - (r < 0);
        return 1;
    }
    (void)c;
    return 0;
}

static value binop(struct ctx *c, int op, value a, value b) {
    switch (op) {
    case OP_ADD:
        if (a.k == V_INT && b.k == V_INT) {
            int64_t r;
            if (__builtin_add_overflow(a.u.i, b.u.i, &r)) rt_fail(c, "integer overflow in +");
            return vint(r);
        }
        if (is_num(&a) && is_num(&b)) return vflt(as_dbl(&a) + as_dbl(&b));
        if (a.k == V_STR && b.k == V_STR) {
            size_t n = a.u.s->len + b.u.s->len;
            str *r = ralloc(c, sizeof *r + n + 1);
            r->len = n;
            memcpy(r->data, a.u.s->data, a.u.s->len);
            memcpy(r->data + a.u.s->len, b.u.s->data, b.u.s->len);
            r->data[n] = '\0';
            return vstrv(r);
        }
        if (a.k == V_LIST && b.k == V_LIST) {
            struct list *r = list_new(c);
            for (size_t i = 0; i < a.u.l->n; i++) list_push(c, r, a.u.l->items[i]);
            for (size_t i = 0; i < b.u.l->n; i++) list_push(c, r, b.u.l->items[i]);
            value v = vnil();
            v.k = V_LIST;
            v.u.l = r;
            return v;
        }
        rt_fail(c, "cannot add %s and %s", type_name(&a), type_name(&b));
    case OP_SUB:
        if (a.k == V_INT && b.k == V_INT) {
            int64_t r;
            if (__builtin_sub_overflow(a.u.i, b.u.i, &r)) rt_fail(c, "integer overflow in -");
            return vint(r);
        }
        if (is_num(&a) && is_num(&b)) return vflt(as_dbl(&a) - as_dbl(&b));
        rt_fail(c, "cannot subtract %s from %s", type_name(&b), type_name(&a));
    case OP_MUL:
        if (a.k == V_INT && b.k == V_INT) {
            int64_t r;
            if (__builtin_mul_overflow(a.u.i, b.u.i, &r)) rt_fail(c, "integer overflow in *");
            return vint(r);
        }
        if (is_num(&a) && is_num(&b)) return vflt(as_dbl(&a) * as_dbl(&b));
        rt_fail(c, "cannot multiply %s and %s", type_name(&a), type_name(&b));
    case OP_DIV:
        if (a.k == V_INT && b.k == V_INT) {
            if (b.u.i == 0) rt_fail(c, "division by zero");
            if (a.u.i == INT64_MIN && b.u.i == -1) rt_fail(c, "integer overflow in /");
            return vint(a.u.i / b.u.i);
        }
        if (is_num(&a) && is_num(&b)) {
            if (as_dbl(&b) == 0.0) rt_fail(c, "division by zero");
            return vflt(as_dbl(&a) / as_dbl(&b));
        }
        rt_fail(c, "cannot divide %s by %s", type_name(&a), type_name(&b));
    case OP_MOD:
        if (a.k == V_INT && b.k == V_INT) {
            if (b.u.i == 0) rt_fail(c, "division by zero");
            if (b.u.i == -1) return vint(0);
            return vint(a.u.i % b.u.i);
        }
        rt_fail(c, "%% needs two integers, got %s and %s", type_name(&a), type_name(&b));
    case OP_EQ: return vbool(values_equal(&a, &b));
    case OP_NE: return vbool(!values_equal(&a, &b));
    case OP_LT: case OP_LE: case OP_GT: case OP_GE: {
        int r = 0;
        if (!compare_values(c, &a, &b, &r)) rt_fail(c, "cannot compare %s and %s", type_name(&a), type_name(&b));
        switch (op) {
        case OP_LT: return vbool(r < 0);
        case OP_LE: return vbool(r <= 0);
        case OP_GT: return vbool(r > 0);
        default: return vbool(r >= 0);
        }
    }
    }
    rt_fail(c, "internal error: unknown operator");
}

static int truth(struct ctx *c, const value *v, const char *what) {
    if (v->k != V_BOOL) rt_fail(c, "%s must be true or false, not %s", what, type_name(v));
    return v->u.b;
}

/* ---------- indexing ---------- */

static value index_get(struct ctx *c, value obj, value idx) {
    if (obj.k == V_LIST) {
        if (idx.k != V_INT) rt_fail(c, "list index must be an int, not %s", type_name(&idx));
        if (idx.u.i < 0 || (size_t)idx.u.i >= obj.u.l->n)
            rt_fail(c, "index %lld is out of range for a list of length %zu", (long long)idx.u.i, obj.u.l->n);
        return obj.u.l->items[idx.u.i];
    }
    if (obj.k == V_STR) {
        if (idx.k != V_INT) rt_fail(c, "string index must be an int, not %s", type_name(&idx));
        if (idx.u.i < 0 || (size_t)idx.u.i >= obj.u.s->len)
            rt_fail(c, "index %lld is out of range for a string of length %zu", (long long)idx.u.i, obj.u.s->len);
        return vstr_of(c, obj.u.s->data + idx.u.i, 1);
    }
    if (obj.k == V_MAP) {
        if (idx.k != V_STR) rt_fail(c, "map key must be a string, not %s", type_name(&idx));
        struct mentry *e = map_find(obj.u.m, idx.u.s);
        if (!e) rt_fail(c, "no key %s in the map", display_str(c, &idx, 1)->data);
        return e->v;
    }
    rt_fail(c, "%s cannot be indexed", type_name(&obj));
}

static void index_set(struct ctx *c, value obj, value idx, value v) {
    if (obj.k == V_LIST) {
        if (idx.k != V_INT) rt_fail(c, "list index must be an int, not %s", type_name(&idx));
        if (idx.u.i < 0 || (size_t)idx.u.i >= obj.u.l->n)
            rt_fail(c, "index %lld is out of range for a list of length %zu", (long long)idx.u.i, obj.u.l->n);
        obj.u.l->items[idx.u.i] = v;
        return;
    }
    if (obj.k == V_MAP) {
        if (idx.k != V_STR) rt_fail(c, "map key must be a string, not %s", type_name(&idx));
        map_set(c, obj.u.m, idx.u.s, v);
        return;
    }
    rt_fail(c, "%s cannot be assigned by index", type_name(&obj));
}

/* ---------- evaluation ---------- */

#define X_PROTO(nm, fn, lo, hi) static value fn(struct ctx *c, value *a, size_t n);
FORGE_BUILTINS(X_PROTO)
#undef X_PROTO


/* Table in the same order as FORGE_BUILTINS, used by call_value. */
#define X_FN(nm, fn, lo, hi) fn,
value (*const forge_builtin_table[])(struct ctx *, value *, size_t) = { FORGE_BUILTINS(X_FN) };
#undef X_FN

static flow exec_stmt(struct ctx *c, struct env *env, node *n);
static flow exec_list(struct ctx *c, struct env *env, node **kids, size_t n);
static value call_value(struct ctx *c, value callee, value *args, size_t nargs);

static flow exec_block(struct ctx *c, struct env *env, node *blk) {
    return exec_list(c, env_new(c, env), blk->kids, blk->nkids);
}

static value eval(struct ctx *c, struct env *env, node *n) {
    c->cur = n;
    switch (n->kind) {
    case N_INT: return vint(n->ival);
    case N_FLT: return vflt(n->fval);
    case N_STR: return vstr_of(c, n->name, n->slen);
    case N_BOOL: return vbool((int)n->ival);
    case N_NIL: return vnil();
    case N_IDENT: {
        value *p = env_find(env, n->name);
        if (p) return *p;
        int bi = builtin_index(n->name);
        if (bi >= 0) { value v = vnil(); v.k = V_BUILTIN; v.u.bi = bi; return v; }
        rt_fail(c, "undefined name '%s'", n->name);
    }
    case N_LIST: {
        struct list *l = list_new(c);
        for (size_t i = 0; i < n->nkids; i++) list_push(c, l, eval(c, env, n->kids[i]));
        value v = vnil();
        v.k = V_LIST;
        v.u.l = l;
        return v;
    }
    case N_MAP: {
        struct map *m = map_new(c);
        for (size_t i = 0; i + 1 < n->nkids; i += 2) {
            value k = eval(c, env, n->kids[i]);
            value v = eval(c, env, n->kids[i + 1]);
            c->cur = n;
            if (k.k != V_STR) rt_fail(c, "map keys must be strings, not %s", type_name(&k));
            map_set(c, m, k.u.s, v);
        }
        value v = vnil();
        v.k = V_MAP;
        v.u.m = m;
        return v;
    }
    case N_LAMBDA: {
        value v = vnil();
        v.k = V_FN;
        v.u.fn = ralloc(c, sizeof *v.u.fn);
        v.u.fn->decl = n;
        v.u.fn->env = env;
        return v;
    }
    case N_UNARY: {
        value x = eval(c, env, n->a);
        c->cur = n;
        if (n->op == OP_NOT) return vbool(!truth(c, &x, "'not' operand"));
        if (x.k == V_INT) {
            if (x.u.i == INT64_MIN) rt_fail(c, "integer overflow in negation");
            return vint(-x.u.i);
        }
        if (x.k == V_FLT) return vflt(-x.u.f);
        rt_fail(c, "cannot negate %s", type_name(&x));
    }
    case N_BINARY: {
        value a = eval(c, env, n->a);
        value b = eval(c, env, n->b);
        c->cur = n;
        return binop(c, n->op, a, b);
    }
    case N_AND: {
        value a = eval(c, env, n->a);
        c->cur = n;
        if (!truth(c, &a, "'and' operand")) return vbool(0);
        value b = eval(c, env, n->b);
        c->cur = n;
        return vbool(truth(c, &b, "'and' operand"));
    }
    case N_OR: {
        value a = eval(c, env, n->a);
        c->cur = n;
        if (truth(c, &a, "'or' operand")) return vbool(1);
        value b = eval(c, env, n->b);
        c->cur = n;
        return vbool(truth(c, &b, "'or' operand"));
    }
    case N_CALL: {
        value callee = eval(c, env, n->a);
        value *args = ralloc(c, (n->nkids ? n->nkids : 1) * sizeof *args);
        for (size_t i = 0; i < n->nkids; i++) args[i] = eval(c, env, n->kids[i]);
        c->cur = n;
        return call_value(c, callee, args, n->nkids);
    }
    case N_INDEX: {
        value obj = eval(c, env, n->a);
        value idx = eval(c, env, n->b);
        c->cur = n;
        return index_get(c, obj, idx);
    }
    default:
        rt_fail(c, "internal error: unexpected expression");
    }
}

static value call_value(struct ctx *c, value callee, value *args, size_t nargs) {
    if (callee.k == V_BUILTIN) {
        const struct builtin_arity *ar = &arities[callee.u.bi];
        if ((int)nargs < ar->min || (ar->max >= 0 && (int)nargs > ar->max))
            rt_fail(c, "%s expects %s arguments, got %zu", ar->name,
                    ar->min == ar->max ? "a fixed number of" : "a different number of", nargs);
        return forge_builtin_table[callee.u.bi](c, args, nargs);
    }
    if (callee.k != V_FN) rt_fail(c, "%s is not a function", type_name(&callee));
    node *fn = callee.u.fn->decl;
    if (nargs != fn->nparams)
        rt_fail(c, "%s expects %zu argument%s, got %zu", fn->name, fn->nparams, fn->nparams == 1 ? "" : "s", nargs);
    if (c->depth + 1 > FORGE_MAX_DEPTH) rt_fail(c, "stack overflow: more than %d nested calls", FORGE_MAX_DEPTH);
    struct env *frame = env_new(c, callee.u.fn->env);
    for (size_t i = 0; i < nargs; i++) env_define(c, frame, fn->params[i], args[i]);
    c->depth++;
    flow f = exec_block(c, frame, fn->b);
    c->depth--;
    if (f == F_RETURN) {
        value r = c->ret;
        c->ret = vnil();
        return r;
    }
    return vnil();
}

static flow exec_list(struct ctx *c, struct env *env, node **kids, size_t n) {
    /* Functions in a block are visible in the whole block, as the checker assumes. */
    for (size_t i = 0; i < n; i++) {
        if (kids[i]->kind == N_FN) {
            value v = vnil();
            v.k = V_FN;
            v.u.fn = ralloc(c, sizeof *v.u.fn);
            v.u.fn->decl = kids[i];
            v.u.fn->env = env;
            env_define(c, env, kids[i]->name, v);
        }
    }
    for (size_t i = 0; i < n; i++) {
        if (kids[i]->kind == N_FN) continue;
        flow f = exec_stmt(c, env, kids[i]);
        if (f != F_NORMAL) return f;
    }
    return F_NORMAL;
}

static flow exec_stmt(struct ctx *c, struct env *env, node *n) {
    c->cur = n;
    switch (n->kind) {
    case N_LET: {
        value v = n->a ? eval(c, env, n->a) : vnil();
        c->cur = n;
        env_define(c, env, n->name, v);
        return F_NORMAL;
    }
    case N_ASSIGN: {
        if (n->a->kind == N_IDENT) {
            value v = eval(c, env, n->b);
            value *slot = env_find(env, n->a->name);
            c->cur = n;
            if (!slot) rt_fail(c, "assignment to undeclared name '%s'", n->a->name);
            *slot = v;
            return F_NORMAL;
        }
        value obj = eval(c, env, n->a->a);
        value idx = eval(c, env, n->a->b);
        value v = eval(c, env, n->b);
        c->cur = n;
        index_set(c, obj, idx, v);
        return F_NORMAL;
    }
    case N_IF: {
        value cond = eval(c, env, n->a);
        c->cur = n;
        if (truth(c, &cond, "condition")) return exec_block(c, env, n->b);
        if (n->c) {
            if (n->c->kind == N_IF) return exec_stmt(c, env, n->c);
            return exec_block(c, env, n->c);
        }
        return F_NORMAL;
    }
    case N_WHILE:
        for (;;) {
            value cond = eval(c, env, n->a);
            c->cur = n;
            if (!truth(c, &cond, "while condition")) return F_NORMAL;
            flow f = exec_block(c, env, n->b);
            if (f == F_BREAK) return F_NORMAL;
            if (f == F_RETURN) return F_RETURN;
        }
    case N_FOR: {
        value it = eval(c, env, n->a);
        c->cur = n;
        struct list *items;
        if (it.k == V_LIST) {
            items = it.u.l;
        } else if (it.k == V_STR) {
            items = list_new(c);
            for (size_t i = 0; i < it.u.s->len; i++) list_push(c, items, vstr_of(c, it.u.s->data + i, 1));
        } else if (it.k == V_MAP) {
            items = list_new(c);
            for (size_t i = 0; i < it.u.m->n; i++) list_push(c, items, vstrv(it.u.m->e[i].key));
        } else {
            rt_fail(c, "cannot loop over %s", type_name(&it));
        }
        for (size_t i = 0; i < items->n; i++) {
            struct env *iter = env_new(c, env);
            env_define(c, iter, n->name, items->items[i]);
            flow f = exec_block(c, iter, n->b);
            if (f == F_BREAK) break;
            if (f == F_RETURN) return F_RETURN;
        }
        return F_NORMAL;
    }
    case N_RETURN:
        c->ret = n->a ? eval(c, env, n->a) : vnil();
        return F_RETURN;
    case N_BREAK: return F_BREAK;
    case N_CONTINUE: return F_CONTINUE;
    case N_EXPR:
        eval(c, env, n->a);
        return F_NORMAL;
    case N_BLOCK:
        return exec_block(c, env, n);
    case N_FN:
        return F_NORMAL;
    default:
        rt_fail(c, "internal error: unexpected statement");
    }
}

/* ---------- builtins ---------- */

static value bi_print(struct ctx *c, value *a, size_t n) {
    for (size_t i = 0; i < n; i++) {
        if (i) out_write(c, " ", 1);
        str *s = display_str(c, &a[i], 0);
        out_write(c, s->data, s->len);
    }
    out_write(c, "\n", 1);
    return vnil();
}

static value bi_len(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k == V_STR) return vint((int64_t)a[0].u.s->len);
    if (a[0].k == V_LIST) return vint((int64_t)a[0].u.l->n);
    if (a[0].k == V_MAP) return vint((int64_t)a[0].u.m->n);
    rt_fail(c, "len needs a string, list or map, not %s", type_name(&a[0]));
}

static value bi_str(struct ctx *c, value *a, size_t n) {
    (void)n;
    return vstrv(display_str(c, &a[0], 0));
}

static value bi_int(struct ctx *c, value *a, size_t n) {
    (void)n;
    value v = a[0];
    if (v.k == V_INT) return v;
    if (v.k == V_BOOL) return vint(v.u.b);
    if (v.k == V_FLT) {
        if (!(v.u.f > -9.2e18 && v.u.f < 9.2e18)) rt_fail(c, "float %s is out of the int range", display_str(c, &v, 0)->data);
        return vint((int64_t)v.u.f);
    }
    if (v.k == V_STR) {
        char *end = NULL;
        errno = 0;
        long long r = strtoll(v.u.s->data, &end, 10);
        if (v.u.s->len == 0 || errno == ERANGE || *end != '\0' || end == v.u.s->data)
            rt_fail(c, "cannot convert %s to an int", display_str(c, &v, 1)->data);
        return vint(r);
    }
    rt_fail(c, "cannot convert %s to an int", type_name(&v));
}

static value bi_float(struct ctx *c, value *a, size_t n) {
    (void)n;
    value v = a[0];
    if (v.k == V_FLT) return v;
    if (v.k == V_INT) return vflt((double)v.u.i);
    if (v.k == V_STR) {
        char *end = NULL;
        double d = strtod(v.u.s->data, &end);
        if (v.u.s->len == 0 || *end != '\0' || end == v.u.s->data || !isfinite(d))
            rt_fail(c, "cannot convert %s to a float", display_str(c, &v, 1)->data);
        return vflt(d);
    }
    rt_fail(c, "cannot convert %s to a float", type_name(&v));
}

static value bi_type(struct ctx *c, value *a, size_t n) {
    (void)n;
    const char *t = type_name(&a[0]);
    return vstr_of(c, t, strlen(t));
}

static value bi_push(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_LIST) rt_fail(c, "push needs a list, not %s", type_name(&a[0]));
    list_push(c, a[0].u.l, a[1]);
    return vnil();
}

static value bi_pop(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_LIST) rt_fail(c, "pop needs a list, not %s", type_name(&a[0]));
    if (a[0].u.l->n == 0) rt_fail(c, "pop from an empty list");
    return a[0].u.l->items[--a[0].u.l->n];
}

static value bi_keys(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_MAP) rt_fail(c, "keys needs a map, not %s", type_name(&a[0]));
    struct list *l = list_new(c);
    for (size_t i = 0; i < a[0].u.m->n; i++) list_push(c, l, vstrv(a[0].u.m->e[i].key));
    value v = vnil();
    v.k = V_LIST;
    v.u.l = l;
    return v;
}

static value bi_has(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_MAP) rt_fail(c, "has needs a map, not %s", type_name(&a[0]));
    if (a[1].k != V_STR) rt_fail(c, "map keys are strings, not %s", type_name(&a[1]));
    return vbool(map_find(a[0].u.m, a[1].u.s) != NULL);
}

static value bi_remove(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_MAP) rt_fail(c, "remove needs a map, not %s", type_name(&a[0]));
    if (a[1].k != V_STR) rt_fail(c, "map keys are strings, not %s", type_name(&a[1]));
    struct map *m = a[0].u.m;
    for (size_t i = 0; i < m->n; i++) {
        if (str_eq(m->e[i].key, a[1].u.s)) {
            memmove(&m->e[i], &m->e[i + 1], (m->n - i - 1) * sizeof *m->e);
            m->n--;
            return vbool(1);
        }
    }
    return vbool(0);
}

static const char *find_sub(const char *hay, size_t hn, const char *needle, size_t nn) {
    if (nn == 0) return hay;
    if (nn > hn) return NULL;
    for (size_t i = 0; i + nn <= hn; i++) if (!memcmp(hay + i, needle, nn)) return hay + i;
    return NULL;
}

static value bi_split(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR || a[1].k != V_STR) rt_fail(c, "split needs two strings");
    if (a[1].u.s->len == 0) rt_fail(c, "split separator must not be empty");
    struct list *l = list_new(c);
    const char *p = a[0].u.s->data, *end = p + a[0].u.s->len;
    for (;;) {
        const char *hit = find_sub(p, (size_t)(end - p), a[1].u.s->data, a[1].u.s->len);
        if (!hit) break;
        list_push(c, l, vstr_of(c, p, (size_t)(hit - p)));
        p = hit + a[1].u.s->len;
    }
    list_push(c, l, vstr_of(c, p, (size_t)(end - p)));
    value v = vnil();
    v.k = V_LIST;
    v.u.l = l;
    return v;
}

static value bi_join(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_LIST) rt_fail(c, "join needs a list, not %s", type_name(&a[0]));
    if (a[1].k != V_STR) rt_fail(c, "join separator must be a string");
    struct sbuf b = {0};
    for (size_t i = 0; i < a[0].u.l->n; i++) {
        if (i) sb_add(c, &b, a[1].u.s->data, a[1].u.s->len);
        display_into(c, &b, &a[0].u.l->items[i], 0, 0);
    }
    return vstrv(str_new(c, b.p ? b.p : "", b.n));
}

static value bi_upper(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR) rt_fail(c, "upper needs a string");
    str *r = str_new(c, a[0].u.s->data, a[0].u.s->len);
    for (size_t i = 0; i < r->len; i++) r->data[i] = (char)toupper((unsigned char)r->data[i]);
    return vstrv(r);
}

static value bi_lower(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR) rt_fail(c, "lower needs a string");
    str *r = str_new(c, a[0].u.s->data, a[0].u.s->len);
    for (size_t i = 0; i < r->len; i++) r->data[i] = (char)tolower((unsigned char)r->data[i]);
    return vstrv(r);
}

static value bi_trim(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR) rt_fail(c, "trim needs a string");
    const char *p = a[0].u.s->data, *e = p + a[0].u.s->len;
    while (p < e && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) p++;
    while (e > p && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\r' || e[-1] == '\n')) e--;
    return vstr_of(c, p, (size_t)(e - p));
}

static value bi_contains(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k == V_STR) {
        if (a[1].k != V_STR) rt_fail(c, "contains needs a string to look for");
        return vbool(find_sub(a[0].u.s->data, a[0].u.s->len, a[1].u.s->data, a[1].u.s->len) != NULL);
    }
    if (a[0].k == V_LIST) {
        for (size_t i = 0; i < a[0].u.l->n; i++) if (values_equal(&a[0].u.l->items[i], &a[1])) return vbool(1);
        return vbool(0);
    }
    rt_fail(c, "contains needs a string or list, not %s", type_name(&a[0]));
}

static value bi_starts_with(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR || a[1].k != V_STR) rt_fail(c, "starts_with needs two strings");
    return vbool(a[1].u.s->len <= a[0].u.s->len && !memcmp(a[0].u.s->data, a[1].u.s->data, a[1].u.s->len));
}

static value bi_ends_with(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR || a[1].k != V_STR) rt_fail(c, "ends_with needs two strings");
    size_t off = a[0].u.s->len - (a[1].u.s->len <= a[0].u.s->len ? a[1].u.s->len : a[0].u.s->len);
    return vbool(a[1].u.s->len <= a[0].u.s->len && !memcmp(a[0].u.s->data + off, a[1].u.s->data, a[1].u.s->len));
}

static value bi_replace(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR || a[1].k != V_STR || a[2].k != V_STR) rt_fail(c, "replace needs three strings");
    if (a[1].u.s->len == 0) rt_fail(c, "replace target must not be empty");
    struct sbuf b = {0};
    const char *p = a[0].u.s->data, *end = p + a[0].u.s->len;
    for (;;) {
        const char *hit = find_sub(p, (size_t)(end - p), a[1].u.s->data, a[1].u.s->len);
        if (!hit) break;
        sb_add(c, &b, p, (size_t)(hit - p));
        sb_add(c, &b, a[2].u.s->data, a[2].u.s->len);
        p = hit + a[1].u.s->len;
    }
    sb_add(c, &b, p, (size_t)(end - p));
    return vstrv(str_new(c, b.p ? b.p : "", b.n));
}

static value bi_substr(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR || a[1].k != V_INT || a[2].k != V_INT) rt_fail(c, "substr needs a string and two ints");
    int64_t start = a[1].u.i, count = a[2].u.i;
    if (start < 0 || count < 0 || (uint64_t)start > a[0].u.s->len || (uint64_t)count > a[0].u.s->len - (uint64_t)start)
        rt_fail(c, "substr range %lld..%lld is outside a string of length %zu", (long long)start,
                (long long)(start + count), a[0].u.s->len);
    return vstr_of(c, a[0].u.s->data + start, (size_t)count);
}

static value bi_abs(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k == V_INT) {
        if (a[0].u.i == INT64_MIN) rt_fail(c, "integer overflow in abs");
        return vint(a[0].u.i < 0 ? -a[0].u.i : a[0].u.i);
    }
    if (a[0].k == V_FLT) return vflt(fabs(a[0].u.f));
    rt_fail(c, "abs needs a number, not %s", type_name(&a[0]));
}

static value bi_min(struct ctx *c, value *a, size_t n) {
    (void)n;
    int r = 0;
    if (!is_num(&a[0]) || !is_num(&a[1]) || !compare_values(c, &a[0], &a[1], &r)) rt_fail(c, "min needs two numbers");
    return r <= 0 ? a[0] : a[1];
}

static value bi_max(struct ctx *c, value *a, size_t n) {
    (void)n;
    int r = 0;
    if (!is_num(&a[0]) || !is_num(&a[1]) || !compare_values(c, &a[0], &a[1], &r)) rt_fail(c, "max needs two numbers");
    return r >= 0 ? a[0] : a[1];
}

static value bi_floor(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k == V_INT) return a[0];
    if (a[0].k != V_FLT) rt_fail(c, "floor needs a number, not %s", type_name(&a[0]));
    double f = floor(a[0].u.f);
    if (!(f > -9.2e18 && f < 9.2e18)) rt_fail(c, "floor result is out of the int range");
    return vint((int64_t)f);
}

static value bi_sqrt(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (!is_num(&a[0])) rt_fail(c, "sqrt needs a number, not %s", type_name(&a[0]));
    double x = as_dbl(&a[0]);
    if (x < 0) rt_fail(c, "sqrt of a negative number");
    return vflt(sqrt(x));
}

static value bi_range(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_INT || a[0].u.i < 0 || a[0].u.i > 1000000) rt_fail(c, "range needs an int from 0 to 1000000");
    struct list *l = list_new(c);
    for (int64_t i = 0; i < a[0].u.i; i++) list_push(c, l, vint(i));
    value v = vnil();
    v.k = V_LIST;
    v.u.l = l;
    return v;
}

static value bi_exit(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_INT) rt_fail(c, "exit needs an int code");
    c->exit_code = (int)(a[0].u.i & 0xff);
    c->jb_code = 2;
    longjmp(*c->jb, 1);
}

static value bi_assert(struct ctx *c, value *a, size_t n) {
    if (a[0].k != V_BOOL) rt_fail(c, "assert needs true or false, not %s", type_name(&a[0]));
    if (a[0].u.b) return vnil();
    if (n == 2) {
        str *m = display_str(c, &a[1], 0);
        rt_fail(c, "assertion failed: %s", m->data);
    }
    rt_fail(c, "assertion failed");
}

static value bi_read_asset(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR) rt_fail(c, "read_asset needs a file name");
    const char *name = a[0].u.s->data;
    size_t len = a[0].u.s->len;
    if (!c->assets) rt_fail(c, "this program has no assets folder");
    if (len == 0 || len > 128 || name[0] == '.' || strstr(name, "..")) rt_fail(c, "invalid asset name");
    for (size_t i = 0; i < len; i++) {
        unsigned char ch = (unsigned char)name[i];
        if (!(isalnum(ch) || ch == '.' || ch == '_' || ch == '-')) rt_fail(c, "invalid asset name");
    }
    char path[PATH_MAX];
    if (snprintf(path, sizeof path, "%s/%s", c->assets, name) >= (int)sizeof path) rt_fail(c, "invalid asset name");
    FILE *f = fopen(path, "rb");
    if (!f) rt_fail(c, "asset '%s' is missing", name);
    struct stat st;
    if (fstat(fileno(f), &st) || !S_ISREG(st.st_mode) || st.st_size > (off_t)(4u * 1024u * 1024u)) {
        fclose(f);
        rt_fail(c, "asset '%s' is not a readable file under 4 MiB", name);
    }
    str *s = ralloc(c, sizeof *s + (size_t)st.st_size + 1);
    size_t got = fread(s->data, 1, (size_t)st.st_size, f);
    fclose(f);
    s->len = got;
    s->data[got] = '\0';
    return vstrv(s);
}

static value bi_error(struct ctx *c, value *a, size_t n) {
    (void)n;
    if (a[0].k != V_STR) rt_fail(c, "error needs a message string");
    rt_fail(c, "%s", a[0].u.s->data);
}


/* ---------- entry points ---------- */

static int setup_ctx(struct ctx *c, forge_program *p, const char *assets, FILE *out, FILE *err, jmp_buf *jb) {
    memset(c, 0, sizeof *c);
    c->heap.limit = FORGE_MAX_HEAP;
    c->out = out;
    c->err = err;
    c->assets = assets;
    c->prog = p;
    c->jb = jb;
    c->ret = vnil();
    c->globals = env_new(c, NULL);
    return 0;
}

/* Defines the top-level declarations: functions first, then lets in order. */
static void run_top_level(struct ctx *c) {
    exec_list(c, c->globals, c->prog->root->kids, c->prog->root->nkids);
}

int forge_run_main(forge_program *p, const char *assets, FILE *out, FILE *err) {
    if (!p) return 1;
    struct ctx c;
    jmp_buf jb;
    if (setjmp(jb)) {
        int code = 1;
        if (c.jb_code == 2) code = c.exit_code;
        else fprintf(err, "%s\n", c.msg);
        arena_free(&c.heap);
        return code;
    }
    setup_ctx(&c, p, assets, out, err, &jb);
    run_top_level(&c);
    if (!forge_has_function(p, "main")) {
        fprintf(err, "error: the program has no main() function\n");
        arena_free(&c.heap);
        return 1;
    }
    value mainfn = *env_find(c.globals, "main");
    call_value(&c, mainfn, NULL, 0);
    fflush(out);
    arena_free(&c.heap);
    return 0;
}

/* Runs one test function. Returns 1 when it failed. */
static int run_one_test(struct ctx *c, node *fn_decl, FILE *out) {
    jmp_buf jb;
    if (setjmp(jb)) {
        fprintf(out, "FAIL %s: %s\n", fn_decl->name, c->msg);
        c->depth = 0;
        c->cur = NULL;
        return 1;
    }
    c->jb = &jb;
    value fn = *env_find(c->globals, fn_decl->name);
    call_value(c, fn, NULL, 0);
    fprintf(out, "ok %s\n", fn_decl->name);
    return 0;
}

int forge_run_tests(forge_program *p, const char *assets, FILE *out, size_t *passed, size_t *failed) {
    *passed = 0;
    *failed = 0;
    if (!p) return 1;
    size_t tests = 0;
    for (size_t i = 0; i < p->root->nkids; i++) {
        node *k = p->root->kids[i];
        if (k->kind == N_FN && !strncmp(k->name, "test_", 5)) tests++;
    }
    if (!tests) return -1;

    struct ctx c;
    jmp_buf setup_jb;
    if (setjmp(setup_jb)) {
        fprintf(out, "FAIL setup: %s\n", c.msg);
        arena_free(&c.heap);
        *failed = 1;
        return 1;
    }
    setup_ctx(&c, p, assets, out, out, &setup_jb);
    run_top_level(&c);

    for (size_t i = 0; i < p->root->nkids; i++) {
        node *k = p->root->kids[i];
        if (k->kind != N_FN || strncmp(k->name, "test_", 5)) continue;
        if (run_one_test(&c, k, out)) (*failed)++;
        else (*passed)++;
    }
    arena_free(&c.heap);
    return *failed ? 1 : 0;
}
