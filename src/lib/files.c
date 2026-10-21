#define _GNU_SOURCE
#include "files.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

int ominx_copy(const char *source, const char *destination) {
    int in = open(source, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (in < 0) return -1;
    struct stat st;
    if (fstat(in, &st)) {
        int saved = errno; close(in); errno = saved; return -1;
    }
    if (!S_ISREG(st.st_mode)) { close(in); errno = EINVAL; return -1; }
    char *temporary;
    if (asprintf(&temporary, "%s.ominx-copy-XXXXXX", destination) < 0) {
        close(in); errno = ENOMEM; return -1;
    }
    int out = mkstemp(temporary);
    if (out < 0) { int saved = errno; free(temporary); close(in); errno = saved; return -1; }
    int result = -1;
    char buffer[65536];
    for (;;) {
        ssize_t count = read(in, buffer, sizeof buffer);
        if (count < 0) { if (errno == EINTR) continue; goto done; }
        if (!count) break;
        for (ssize_t offset = 0; offset < count;) {
            ssize_t written = write(out, buffer + offset, (size_t)(count - offset));
            if (written < 0) { if (errno == EINTR) continue; goto done; }
            if (!written) { errno = EIO; goto done; }
            offset += written;
        }
    }
    /* Drop executable/setuid bits: a copied document is not implicitly runnable. */
    if (fchmod(out, st.st_mode & 0666) || fsync(out)) goto done;
    /* link is atomic and refuses existing files, directories and symlinks. */
    if (link(temporary, destination)) goto done;
    result = 0;
done:;
    int saved = errno;
    close(out); close(in);
    unlink(temporary);
    free(temporary);
    errno = saved;
    return result;
}

int ominx_move(const char *source, const char *destination) {
    return (int)syscall(SYS_renameat2, AT_FDCWD, source, AT_FDCWD, destination, 1 /* RENAME_NOREPLACE */);
}
