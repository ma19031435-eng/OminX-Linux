/* Original PE/MSI header inspector. Repository license applies. */
#define _GNU_SOURCE
#include "pe.h"
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define HEADER_WINDOW (2u * 1024u * 1024u)
#define MAX_E_LFANEW (1024u * 1024u)
#define MAX_SECTIONS 96u
#define MAX_OPTIONAL 4096u

static unsigned short u16le(const unsigned char *p) {
    return (unsigned short)(p[0] | ((unsigned)p[1] << 8));
}
static unsigned u32le(const unsigned char *p) {
    return p[0] | ((unsigned)p[1] << 8) | ((unsigned)p[2] << 16) |
           ((unsigned)p[3] << 24);
}
static int malformed(struct ominx_pe_info *info, const char *reason) {
    info->kind = OMINX_PE_INVALID;
    char *out = info->error;
    size_t i = 0;
    while (reason[i] && i + 1 < sizeof info->error) {
        out[i] = reason[i];
        i++;
    }
    out[i] = 0;
    return -1;
}
static const unsigned char ole_magic[8] = {0xd0, 0xcf, 0x11, 0xe0,
                                           0xa1, 0xb1, 0x1a, 0xe1};

int ominx_pe_inspect_bytes(const unsigned char *data, size_t length,
                           unsigned long long file_size,
                           struct ominx_pe_info *info) {
    if (!info) return -1;
    memset(info, 0, sizeof *info);
    info->kind = OMINX_PE_UNKNOWN;
    info->file_size = file_size;
    if (!data || !length) {
        if (file_size) return malformed(info, "truncated-header");
        return malformed(info, "empty-file");
    }
    if (length >= sizeof ole_magic && !memcmp(data, ole_magic, sizeof ole_magic)) {
        info->kind = OMINX_PE_MSI;
        if (file_size < 512) return malformed(info, "truncated-msi");
        return 0;
    }
    if (length < 2 || data[0] != 'M' || data[1] != 'Z') return 0; /* Unknown. */
    if (file_size < 64 || length < 64) return malformed(info, "truncated-dos-header");
    unsigned e_lfanew = u32le(data + 0x3c);
    if (e_lfanew < 64 || e_lfanew > MAX_E_LFANEW)
        return malformed(info, "bad-pe-offset");
    if ((unsigned long long)e_lfanew + 24 > file_size)
        return malformed(info, "truncated-pe-header");
    if ((size_t)e_lfanew + 24 > length)
        return malformed(info, "truncated-header");
    const unsigned char *pe = data + e_lfanew;
    if (memcmp(pe, "PE\0\0", 4)) return malformed(info, "bad-pe-signature");
    const unsigned char *coff = pe + 4;
    unsigned machine = u16le(coff);
    unsigned sections = u16le(coff + 2);
    unsigned optional_size = u16le(coff + 16);
    unsigned characteristics = u16le(coff + 18);
    if (!sections || sections > MAX_SECTIONS)
        return malformed(info, "bad-section-count");
    if (optional_size > MAX_OPTIONAL)
        return malformed(info, "bad-optional-header");
    if ((unsigned long long)e_lfanew + 24 + optional_size +
            (unsigned long long)sections * 40 > file_size)
        return malformed(info, "truncated-section-table");
    info->sections = sections;
    switch (machine) {
        case 0x014c: info->arch = OMINX_PE_ARCH_I386; info->bits = 32; break;
        case 0x8664: info->arch = OMINX_PE_ARCH_AMD64; info->bits = 64; break;
        case 0x01c0: case 0x01c4: info->arch = OMINX_PE_ARCH_ARM; info->bits = 32; break;
        case 0xaa64: info->arch = OMINX_PE_ARCH_ARM64; info->bits = 64; break;
        case 0x0200: info->arch = OMINX_PE_ARCH_IA64; info->bits = 64; break;
        default: return malformed(info, "unsupported-machine");
    }
    info->kind = (characteristics & 0x2000) ? OMINX_PE_DLL : OMINX_PE_EXE;
    if (!optional_size) return 0;
    if (optional_size < 2) return malformed(info, "bad-optional-header");
    if ((size_t)e_lfanew + 24 + optional_size > length)
        return malformed(info, "truncated-header");
    const unsigned char *opt = coff + 20;
    unsigned magic = u16le(opt);
    size_t subsystem_at, directories_at, count_at;
    if (magic == 0x10b) {         /* PE32 */
        subsystem_at = 68; count_at = 92; directories_at = 96;
        if (info->bits == 64) return malformed(info, "bits-mismatch");
    } else if (magic == 0x20b) {  /* PE32+ */
        subsystem_at = 68; count_at = 108; directories_at = 112;
        if (info->bits == 32) return malformed(info, "bits-mismatch");
    } else if (magic == 0x107) {  /* ROM image: no directories. */
        return 0;
    } else {
        return malformed(info, "bad-optional-magic");
    }
    if (optional_size > subsystem_at + 2)
        info->subsystem = u16le(opt + subsystem_at);
    if (optional_size > count_at + 4) {
        unsigned directories = u32le(opt + count_at);
        /* Directory 14 is the CLR runtime header. Only trust entries that
           lie completely inside the declared optional header. */
        if (directories > 14 &&
            directories_at + 15 * 8 <= optional_size) {
            unsigned clr_rva = u32le(opt + directories_at + 14 * 8);
            unsigned clr_size = u32le(opt + directories_at + 14 * 8 + 4);
            info->dotnet = clr_rva && clr_size;
        }
    }
    return 0;
}

int ominx_pe_inspect_path(const char *path, struct ominx_pe_info *info) {
    if (!path || !info) { errno = EINVAL; return -2; }
    memset(info, 0, sizeof *info);
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) return -2;
    struct stat st;
    if (fstat(fd, &st)) {
        int saved = errno; close(fd); errno = saved; return -2;
    }
    if (!S_ISREG(st.st_mode)) { close(fd); errno = EINVAL; return -2; }
    size_t want = HEADER_WINDOW;
    if (st.st_size >= 0 && (unsigned long long)st.st_size < want)
        want = (size_t)st.st_size;
    unsigned char *buffer = malloc(want ? want : 1);
    if (!buffer) { close(fd); errno = ENOMEM; return -2; }
    size_t done = 0;
    while (done < want) {
        ssize_t count = read(fd, buffer + done, want - done);
        if (count < 0) {
            if (errno == EINTR) continue;
            int saved = errno; free(buffer); close(fd); errno = saved; return -2;
        }
        if (!count) break;
        done += (size_t)count;
    }
    close(fd);
    int result = ominx_pe_inspect_bytes(buffer, done,
                                        (unsigned long long)st.st_size, info);
    free(buffer);
    return result;
}

const char *ominx_pe_kind_name(int kind) {
    switch (kind) {
        case OMINX_PE_EXE: return "exe";
        case OMINX_PE_DLL: return "dll";
        case OMINX_PE_MSI: return "msi";
        case OMINX_PE_INVALID: return "invalid";
        default: return "unknown";
    }
}
const char *ominx_pe_arch_name(int arch) {
    switch (arch) {
        case OMINX_PE_ARCH_I386: return "i386";
        case OMINX_PE_ARCH_AMD64: return "x86-64";
        case OMINX_PE_ARCH_ARM: return "arm";
        case OMINX_PE_ARCH_ARM64: return "arm64";
        case OMINX_PE_ARCH_IA64: return "ia64";
        default: return "unknown";
    }
}
int ominx_pe_suffix(const char *path) {
    if (!path) return 0;
    size_t length = 0;
    while (path[length]) length++;
    if (length < 4 || path[length - 4] != '.') return 0;
    const char *suffix = path + length - 3;
    char lowered[4] = {0, 0, 0, 0};
    for (int i = 0; i < 3; i++) {
        char c = suffix[i];
        lowered[i] = (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c;
    }
    if (!memcmp(lowered, "exe", 4)) return 1;
    if (!memcmp(lowered, "msi", 4)) return 2;
    if (!memcmp(lowered, "dll", 4)) return 3;
    return 0;
}
