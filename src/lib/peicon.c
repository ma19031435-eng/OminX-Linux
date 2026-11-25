/* Icon extraction for Windows programs. Reads the PE resource directory, picks
   the largest icon, and writes it as a PNG. Pure C: no zlib, so the PNG uses
   stored deflate blocks. Icons are at most 256 pixels, so that stays small. */
#include "peicon.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define FILE_MAX (256u * 1024u * 1024u)
#define RT_ICON 3
#define RT_GROUP_ICON 14
#define PNG_MAX (512u * 1024u)
#define MAX_ENTRIES 4096

static void set_reason(char *reason, size_t size, const char *text) {
    if (!size) return;
    snprintf(reason, size, "%s", text);
}

static uint16_t rd16(const unsigned char *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t rd32(const unsigned char *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void wr32be(unsigned char *p, uint32_t v) {
    p[0] = (unsigned char)(v >> 24); p[1] = (unsigned char)(v >> 16);
    p[2] = (unsigned char)(v >> 8); p[3] = (unsigned char)v;
}
static int in_range(size_t off, size_t len, size_t total) {
    return off <= total && len <= total - off;
}

/* ---- PE resources ---- */

struct pe_view {
    const unsigned char *f;
    size_t n;
    size_t res_off;   /* file offset of the resource directory root */
    size_t res_size;
};

/* Maps an RVA to a file offset through the section table. */
static int rva_to_off(const struct pe_view *v, uint32_t rva, uint32_t len, size_t *off) {
    size_t e_lfanew = rd32(v->f + 0x3c);
    if (!in_range(e_lfanew, 24, v->n)) return -1;
    const unsigned char *coff = v->f + e_lfanew + 4;
    unsigned sections = rd16(coff + 2);
    unsigned opt_size = rd16(coff + 16);
    const unsigned char *sec = coff + 20 + opt_size;
    if (!in_range((size_t)(sec - v->f), (size_t)sections * 40, v->n)) return -1;
    for (unsigned i = 0; i < sections; i++, sec += 40) {
        uint32_t va = rd32(sec + 12), vsize = rd32(sec + 8), raw_size = rd32(sec + 16), raw = rd32(sec + 20);
        uint32_t span = vsize > raw_size ? vsize : raw_size;
        if (rva >= va && (uint64_t)rva + len <= (uint64_t)va + span) {
            size_t candidate = (size_t)raw + (rva - va);
            if (!in_range(candidate, len, v->n)) return -1;
            *off = candidate;
            return 0;
        }
    }
    return -1;
}

/* Finds the child with @id in a resource directory. Returns 0 and fills
   @child (file offset) and @is_dir. */
static int find_id(const struct pe_view *v, size_t dir, uint32_t id, size_t *child, int *is_dir) {
    if (!in_range(dir, 16, v->n)) return -1;
    unsigned named = rd16(v->f + dir + 12), ids = rd16(v->f + dir + 14);
    unsigned count = named + ids;
    if (count > MAX_ENTRIES) return -1;
    for (unsigned i = 0; i < count; i++) {
        size_t e = dir + 16 + (size_t)i * 8;
        if (!in_range(e, 8, v->n)) return -1;
        uint32_t name = rd32(v->f + e), off = rd32(v->f + e + 4);
        if (name & 0x80000000u) continue; /* named entry: not used for icons */
        if (name != id) continue;
        size_t target = v->res_off + (off & 0x7fffffffu);
        if (!in_range(target, 16, v->n)) return -1;
        *child = target;
        *is_dir = (off & 0x80000000u) != 0;
        return 0;
    }
    return -1;
}

/* First entry of a directory, of either kind. */
static int first_child(const struct pe_view *v, size_t dir, size_t *child, int *is_dir, uint32_t *id) {
    if (!in_range(dir, 16, v->n)) return -1;
    unsigned count = rd16(v->f + dir + 12) + rd16(v->f + dir + 14);
    if (!count || count > MAX_ENTRIES) return -1;
    size_t e = dir + 16;
    if (!in_range(e, 8, v->n)) return -1;
    uint32_t name = rd32(v->f + e), off = rd32(v->f + e + 4);
    if (name & 0x80000000u) return -1;
    *id = name;
    size_t target = v->res_off + (off & 0x7fffffffu);
    if (!in_range(target, 16, v->n)) return -1;
    *child = target;
    *is_dir = (off & 0x80000000u) != 0;
    return 0;
}

/* Resolves a data entry (file offset of an IMAGE_RESOURCE_DATA_ENTRY) to the bytes it names. */
static int data_bytes(const struct pe_view *v, size_t entry, const unsigned char **bytes, size_t *len) {
    if (!in_range(entry, 16, v->n)) return -1;
    uint32_t rva = rd32(v->f + entry), size = rd32(v->f + entry + 4);
    size_t off;
    if (size == 0 || size > PNG_MAX * 4u) return -1;
    if (rva_to_off(v, rva, size, &off)) return -1;
    *bytes = v->f + off;
    *len = size;
    return 0;
}

/* ---- image conversion ---- */

static uint32_t crc_table[256];
static int crc_ready;

static uint32_t crc32_of(const unsigned char *p, size_t n, uint32_t crc) {
    if (!crc_ready) {
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int k = 0; k < 8; k++) c = (c & 1) ? 0xedb88320u ^ (c >> 1) : c >> 1;
            crc_table[i] = c;
        }
        crc_ready = 1;
    }
    crc ^= 0xffffffffu;
    for (size_t i = 0; i < n; i++) crc = crc_table[(crc ^ p[i]) & 0xff] ^ (crc >> 8);
    return crc ^ 0xffffffffu;
}

static void put_chunk(unsigned char *out, size_t *pos, const char *type, const unsigned char *data, size_t len) {
    wr32be(out + *pos, (uint32_t)len);
    memcpy(out + *pos + 4, type, 4);
    if (len) memcpy(out + *pos + 8, data, len);
    uint32_t crc = crc32_of((const unsigned char *)type, 4, 0);
    crc = crc32_of(data, len, crc);
    wr32be(out + *pos + 8 + len, crc);
    *pos += 12 + len;
}

/* Encodes RGBA rows as a PNG with stored (uncompressed) deflate blocks. */
static int encode_png(const unsigned char *rgba, int w, int h, unsigned char **out, size_t *out_len) {
    size_t row = (size_t)w * 4 + 1;
    size_t raw_len = row * (size_t)h;
    unsigned blocks = (unsigned)((raw_len + 65534) / 65535);
    size_t zlen = 2 + raw_len + 5u * blocks + 4;
    size_t total = 8 + (12 + 13) + (12 + zlen) + 12;
    unsigned char *png = malloc(total);
    unsigned char *raw = malloc(raw_len);
    if (!png || !raw) { free(png); free(raw); return -1; }
    for (int y = 0; y < h; y++) {
        raw[(size_t)y * row] = 0; /* filter: none */
        memcpy(raw + (size_t)y * row + 1, rgba + (size_t)y * w * 4, (size_t)w * 4);
    }
    size_t pos = 0;
    static const unsigned char sig[8] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'};
    memcpy(png, sig, 8);
    pos = 8;
    unsigned char ihdr[13];
    wr32be(ihdr, (uint32_t)w);
    wr32be(ihdr + 4, (uint32_t)h);
    ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    put_chunk(png, &pos, "IHDR", ihdr, sizeof ihdr);

    /* zlib stream: header, stored blocks, Adler-32 of the raw data. */
    unsigned char *z = malloc(zlen);
    if (!z) { free(png); free(raw); return -1; }
    size_t zp = 0;
    z[zp++] = 0x78;
    z[zp++] = 0x01;
    size_t done = 0;
    while (done < raw_len || (raw_len == 0 && done == 0)) {
        size_t chunk = raw_len - done;
        if (chunk > 65535) chunk = 65535;
        int last = done + chunk >= raw_len;
        z[zp++] = last ? 1 : 0;
        z[zp++] = (unsigned char)(chunk & 0xff);
        z[zp++] = (unsigned char)(chunk >> 8);
        z[zp++] = (unsigned char)(~chunk & 0xff);
        z[zp++] = (unsigned char)((~chunk >> 8) & 0xff);
        memcpy(z + zp, raw + done, chunk);
        zp += chunk;
        done += chunk;
        if (last) break;
    }
    uint32_t a = 1, b = 0;
    for (size_t i = 0; i < raw_len; i++) { a = (a + raw[i]) % 65521u; b = (b + a) % 65521u; }
    wr32be(z + zp, (b << 16) | a);
    zp += 4;
    put_chunk(png, &pos, "IDAT", z, zp);
    put_chunk(png, &pos, "IEND", NULL, 0);
    free(z);
    free(raw);
    *out = png;
    *out_len = pos;
    return 0;
}

/* Converts a DIB icon (BITMAPINFOHEADER, no palette, height doubled for the mask) to PNG. */
static int dib_to_png(const unsigned char *d, size_t n, unsigned char **out, size_t *out_len, char *reason, size_t rs) {
    if (n < 40) { set_reason(reason, rs, "icon-format-unsupported"); return -1; }
    uint32_t bisize = rd32(d);
    int32_t w = (int32_t)rd32(d + 4), h2 = (int32_t)rd32(d + 8);
    uint16_t bpp = rd16(d + 14);
    uint32_t compression = rd32(d + 16);
    if (bisize < 40 || compression != 0 || (bpp != 32 && bpp != 24)) { set_reason(reason, rs, "icon-format-unsupported"); return -1; }
    if (w <= 0 || w > 256 || h2 <= 0 || (h2 & 1) || h2 / 2 > 256) { set_reason(reason, rs, "icon-format-unsupported"); return -1; }
    int h = h2 / 2;
    size_t stride = (((size_t)w * bpp + 31) / 32) * 4;
    size_t mask_stride = (((size_t)w + 31) / 32) * 4;
    size_t xor_off = bisize;
    if (!in_range(xor_off, stride * (size_t)h, n)) { set_reason(reason, rs, "pe-unreadable"); return -1; }
    size_t mask_off = xor_off + stride * (size_t)h;
    int has_mask = in_range(mask_off, mask_stride * (size_t)h, n);

    unsigned char *rgba = malloc((size_t)w * h * 4);
    if (!rgba) { set_reason(reason, rs, "out-of-memory"); return -1; }
    int any_alpha = 0;
    for (int y = 0; y < h; y++) {
        const unsigned char *src = d + xor_off + stride * (size_t)(h - 1 - y); /* DIB rows are bottom-up */
        const unsigned char *mask = has_mask ? d + mask_off + mask_stride * (size_t)(h - 1 - y) : NULL;
        for (int x = 0; x < w; x++) {
            unsigned char *px = rgba + ((size_t)y * w + x) * 4;
            const unsigned char *s = src + (size_t)x * (bpp / 8);
            px[0] = s[2]; px[1] = s[1]; px[2] = s[0];
            px[3] = bpp == 32 ? s[3] : 255;
            if (bpp == 32 && px[3]) any_alpha = 1;
            if (bpp == 24 && mask) px[3] = ((mask[x / 8] >> (7 - x % 8)) & 1) ? 0 : 255;
        }
    }
    /* Many 32-bit icons leave alpha at zero and use the AND mask instead. */
    if (bpp == 32 && !any_alpha && has_mask) {
        for (int y = 0; y < h; y++) {
            const unsigned char *mask = d + mask_off + mask_stride * (size_t)(h - 1 - y);
            for (int x = 0; x < w; x++)
                rgba[((size_t)y * w + x) * 4 + 3] = ((mask[x / 8] >> (7 - x % 8)) & 1) ? 0 : 255;
        }
    }
    int rc = encode_png(rgba, w, h, out, out_len);
    free(rgba);
    if (rc) set_reason(reason, rs, "out-of-memory");
    return rc;
}

/* ---- top level ---- */

int ominx_pe_extract_icon(const char *exe_path, const char *png_path, char *reason, size_t reason_size) {
    FILE *f = fopen(exe_path, "rb");
    if (!f) { set_reason(reason, reason_size, "pe-unreadable"); return -1; }
    if (fseek(f, 0, SEEK_END)) { fclose(f); set_reason(reason, reason_size, "pe-unreadable"); return -1; }
    long size = ftell(f);
    if (size < 64 || (unsigned long)size > FILE_MAX || fseek(f, 0, SEEK_SET)) { fclose(f); set_reason(reason, reason_size, "pe-unreadable"); return -1; }
    unsigned char *file = malloc((size_t)size);
    if (!file) { fclose(f); set_reason(reason, reason_size, "out-of-memory"); return -1; }
    if (fread(file, 1, (size_t)size, f) != (size_t)size) { free(file); fclose(f); set_reason(reason, reason_size, "pe-unreadable"); return -1; }
    fclose(f);

    int rc = -1;
    unsigned char *png = NULL;
    size_t png_len = 0;
    struct pe_view v = {file, (size_t)size, 0, 0};
    if (memcmp(file, "MZ", 2) || !in_range(0x3c, 4, v.n)) { set_reason(reason, reason_size, "pe-unreadable"); goto done; }
    size_t e_lfanew = rd32(file + 0x3c);
    if (!in_range(e_lfanew, 24, v.n) || memcmp(file + e_lfanew, "PE\0\0", 4)) { set_reason(reason, reason_size, "pe-unreadable"); goto done; }
    const unsigned char *coff = file + e_lfanew + 4;
    uint16_t opt_size = rd16(coff + 16);
    const unsigned char *opt = coff + 20;
    if (!in_range((size_t)(opt - file), opt_size, v.n) || opt_size < 2) { set_reason(reason, reason_size, "pe-unreadable"); goto done; }
    uint16_t magic = rd16(opt);
    size_t dd_at = magic == 0x20b ? 112 : magic == 0x10b ? 96 : 0;
    if (!dd_at || opt_size < dd_at + 3 * 8 + 8) { set_reason(reason, reason_size, "no-icon"); goto done; }
    uint32_t rsrc_rva = rd32(opt + dd_at + 2 * 8), rsrc_size = rd32(opt + dd_at + 2 * 8 + 4);
    if (!rsrc_rva || !rsrc_size) { set_reason(reason, reason_size, "no-icon"); goto done; }
    if (rva_to_off(&v, rsrc_rva, rsrc_size, &v.res_off)) { set_reason(reason, reason_size, "pe-unreadable"); goto done; }
    v.res_size = rsrc_size;

    /* Group icon: the directory of icon sizes, under type RT_GROUP_ICON. */
    size_t group_type, group_dir, group_data;
    int is_dir;
    uint32_t id;
    if (find_id(&v, v.res_off, RT_GROUP_ICON, &group_type, &is_dir) || !is_dir) { set_reason(reason, reason_size, "no-icon"); goto done; }
    if (first_child(&v, group_type, &group_dir, &is_dir, &id) || !is_dir) { set_reason(reason, reason_size, "no-icon"); goto done; }
    if (first_child(&v, group_dir, &group_data, &is_dir, &id) || is_dir) { set_reason(reason, reason_size, "no-icon"); goto done; }
    const unsigned char *group;
    size_t group_len;
    if (data_bytes(&v, group_data, &group, &group_len) || group_len < 6) { set_reason(reason, reason_size, "pe-unreadable"); goto done; }
    unsigned count = rd16(group + 4);
    if (group_len < 6 + (size_t)count * 14) { set_reason(reason, reason_size, "pe-unreadable"); goto done; }
    unsigned best_id = 0, best_w = 0, best_bits = 0;
    int found = 0;
    for (unsigned i = 0; i < count; i++) {
        const unsigned char *e = group + 6 + (size_t)i * 14;
        unsigned w = e[0] ? e[0] : 256;
        unsigned bits = rd16(e + 6);
        if (!found || w > best_w || (w == best_w && bits > best_bits)) {
            found = 1;
            best_w = w;
            best_bits = bits;
            best_id = rd16(e + 12);
        }
    }
    if (!found) { set_reason(reason, reason_size, "no-icon"); goto done; }

    /* The image with that id, under type RT_ICON. */
    size_t icon_type, icon_dir, icon_data;
    if (find_id(&v, v.res_off, RT_ICON, &icon_type, &is_dir) || !is_dir) { set_reason(reason, reason_size, "no-icon"); goto done; }
    if (find_id(&v, icon_type, best_id, &icon_dir, &is_dir) || !is_dir) { set_reason(reason, reason_size, "no-icon"); goto done; }
    if (first_child(&v, icon_dir, &icon_data, &is_dir, &id) || is_dir) { set_reason(reason, reason_size, "no-icon"); goto done; }
    const unsigned char *image;
    size_t image_len;
    if (data_bytes(&v, icon_data, &image, &image_len)) { set_reason(reason, reason_size, "pe-unreadable"); goto done; }

    if (image_len >= 8 && !memcmp(image, "\x89PNG\r\n\x1a\n", 8)) {
        if (image_len > PNG_MAX) { set_reason(reason, reason_size, "icon-too-large"); goto done; }
        png = malloc(image_len);
        if (!png) { set_reason(reason, reason_size, "out-of-memory"); goto done; }
        memcpy(png, image, image_len);
        png_len = image_len;
    } else if (dib_to_png(image, image_len, &png, &png_len, reason, reason_size)) {
        goto done;
    }
    if (png_len > PNG_MAX) { set_reason(reason, reason_size, "icon-too-large"); goto done; }

    char tmp[4096];
    if (snprintf(tmp, sizeof tmp, "%s.tmp", png_path) >= (int)sizeof tmp) { set_reason(reason, reason_size, "path-too-long"); goto done; }
    FILE *out = fopen(tmp, "wb");
    if (!out) { set_reason(reason, reason_size, "output-unwritable"); goto done; }
    if (fwrite(png, 1, png_len, out) != png_len || fclose(out) != 0) { unlink(tmp); set_reason(reason, reason_size, "output-unwritable"); goto done; }
    if (rename(tmp, png_path)) { unlink(tmp); set_reason(reason, reason_size, "output-unwritable"); goto done; }
    rc = 0;
done:
    free(png);
    free(file);
    return rc;
}
