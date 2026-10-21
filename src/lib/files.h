#ifndef OMINX_FILES_H
#define OMINX_FILES_H
/* No overwrite, no recursive traversal. Failure returns -1 and sets errno. */
int ominx_copy(const char *source, const char *destination);
int ominx_move(const char *source, const char *destination);
#endif
