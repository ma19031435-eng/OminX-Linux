#ifndef OMINX_PEICON_H
#define OMINX_PEICON_H
#include <stddef.h>

/* Copies the largest icon of a Windows program to a PNG file at @png_path.
   Handles PNG-format icons and 24/32-bit bitmap icons, which covers current
   programs. Other formats report "icon-format-unsupported" and leave the app
   with the generic icon. Returns 0 when written, or -1 with a short reason in
   @reason. Nothing is left behind on failure. */
int ominx_pe_extract_icon(const char *exe_path, const char *png_path, char *reason, size_t reason_size);

#endif
