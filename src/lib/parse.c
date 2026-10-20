#include "parse.h"
#include <ctype.h>

int ominx_parse(char *line, char **args, int capacity) {
    char *read = line, *write = line;
    int n = 0;
    while (*read) {
        while (isspace((unsigned char)*read)) read++;
        if (!*read) break;
        if (n >= capacity - 1) return -2;
        args[n++] = write;
        char quote = 0;
        while (*read) {
            char c = *read++;
            if (!quote && isspace((unsigned char)c)) break;
            if (c == '\\' && quote != '\'') {
                if (!*read || *read == '\n') return -1;
                *write++ = *read++;
            } else if ((c == '\'' || c == '"') && (!quote || quote == c)) {
                quote = quote ? 0 : c;
            } else {
                *write++ = c;
            }
        }
        if (quote) return -1;
        *write++ = 0;
    }
    args[n] = 0;
    return n;
}
