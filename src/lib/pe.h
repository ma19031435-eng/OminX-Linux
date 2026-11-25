#ifndef OMINX_PE_H
#define OMINX_PE_H
#include <stddef.h>
/* Original read-only Windows file identification.
   Inspects headers only; never loads, maps executable sections or follows
   embedded paths. Used before any file is handed to Wine/Proton so the
   console, file manager and desktop can refuse clearly wrong files. */
enum ominx_pe_kind {
    OMINX_PE_UNKNOWN = 0, /* Not a Windows executable or installer. */
    OMINX_PE_EXE = 1,     /* Portable Executable program. */
    OMINX_PE_DLL = 2,     /* Library: installable material, never run directly. */
    OMINX_PE_MSI = 3,     /* Windows Installer package (OLE compound file). */
    OMINX_PE_INVALID = 4  /* Looks like one of the above but is malformed. */
};
enum ominx_pe_arch {
    OMINX_PE_ARCH_UNKNOWN = 0,
    OMINX_PE_ARCH_I386 = 1,
    OMINX_PE_ARCH_AMD64 = 2,
    OMINX_PE_ARCH_ARM = 3,
    OMINX_PE_ARCH_ARM64 = 4,
    OMINX_PE_ARCH_IA64 = 5
};
struct ominx_pe_info {
    int kind;           /* enum ominx_pe_kind */
    int arch;           /* enum ominx_pe_arch */
    int bits;           /* 32 or 64 for PE files, otherwise 0. */
    int subsystem;      /* PE subsystem: 2 = GUI, 3 = console, 0 = unknown. */
    int dotnet;         /* Has a CLR (.NET) data directory. */
    unsigned sections;  /* Number of PE sections (sanity checked). */
    unsigned long long file_size;
    char error[64];     /* Stable machine-readable reason when INVALID. */
};
/* Classify an in-memory header window. @length may be smaller than
   @file_size; the parser never reads past @length and reports
   "truncated-header" if the real header needs more. Returns 0 when the
   file was classified (including UNKNOWN), -1 when malformed. */
int ominx_pe_inspect_bytes(const unsigned char *data, size_t length,
                           unsigned long long file_size,
                           struct ominx_pe_info *info);
/* Open (without following a final symlink race into special files),
   require a regular file, read a bounded header window and classify.
   Returns 0 when classified, -1 on malformed headers, -2 on I/O or
   file-type refusal with errno set. */
int ominx_pe_inspect_path(const char *path, struct ominx_pe_info *info);
const char *ominx_pe_kind_name(int kind);
const char *ominx_pe_arch_name(int arch);
/* Filename suffix hint only: 1 for .exe, 2 for .msi, 3 for .dll, else 0.
   Case-insensitive. Always confirm with ominx_pe_inspect_* first. */
int ominx_pe_suffix(const char *path);
#endif
