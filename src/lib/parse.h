#ifndef OMINX_PARSE_H
#define OMINX_PARSE_H
/* In-place tokenization. -1: malformed quoting, -2: argument capacity exceeded. */
int ominx_parse(char *line, char **args, int capacity);
#endif
