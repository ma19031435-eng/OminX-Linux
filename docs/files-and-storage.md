# OminX Files: original backend and Windows-volume reads

This increment adds a separately executable, original C file-management backend to
the independent source-built image. It is the filesystem layer for a later desktop
file manager, not a claim that a graphical application or KDE session is included.
No distro libraries or package-manager dependencies are added to the target.

## Commands

The initramfs contains `/bin/ominx-files`. The OminX console aliases it as `files`:

```text
files help
files list /root
files info "/root/Project notes.txt"
files mkdir "/root/New folder"
files copy "/mnt/data/Windows Notes.txt" "/root/Imported notes.txt"
files move "/root/Imported notes.txt" "/root/Renamed notes.txt"
files remove --confirm "/root/Renamed notes.txt"
```

Normal boots now run as `ominx`, with `/home/ominx` as the working directory.
Use that path for ordinary documents. Examples involving `/root`, data mounting
or importing a mounted Windows volume below require explicit **root recovery**.
See [session policy](sessions.md); no unprivileged mount broker exists yet.

The console now supports single/double-quoted arguments and backslash escapes.
Single quotes preserve backslashes literally. Unterminated quotes/trailing escapes
are rejected. This is not a POSIX shell: pipes, redirection, variable expansion,
globbing and command substitution are not supported. Unicode names are carried as
UTF-8 bytes. A Windows-style `C:\...` path is not translated to a Linux mount path.

### Safety semantics

- `copy` handles regular files only and rejects symlink sources and special files.
  It writes a temporary file alongside the destination, syncs the file data, then
  publishes it with an atomic no-overwrite hard link. Existing files, directories
  and symlink destinations are never overwritten. Failed copies clean up their
  temporary file during normal error handling. A process crash can leave a temp file.
- Copies retain read/write permission bits but drop executable and special bits.
  Ownership, timestamps, ACLs, alternate streams, extended attributes and sparse
  layout are not preserved. This is a document copy operation, not a backup tool.
- `move` uses Linux `renameat2(RENAME_NOREPLACE)`. It cannot overwrite a destination
  and refuses cross-filesystem moves; copy explicitly rather than risking an
  implicit copy-and-delete operation.
- `remove` requires `--confirm`, never recursively deletes and refuses directories.
  It unlinks a symlink itself rather than its target. There is no trash/undo yet.
- The console's `cp` and `mv` now use the same no-overwrite implementation. The
  explicit `write` command still replaces its named file, and `rm` is unchanged.
- These commands execute with the caller's permissions. They are not a sandbox or
  a substitute for user accounts and access control; recovery consoles remain privileged, while normal live sessions run as UID 1000. Recursive browsing and adversarial shared-directory isolation
  must be designed before exposing a network service or multi-user desktop.

### Backend response contract

Except `help` and usage errors, responses are JSON. Success exits 0, operation
failure exits 1, and incorrect invocation exits 2. Example:

```json
{"entries":[{"name":"Project notes.txt","name_hex":"50726f6a656374206e6f7465732e747874","type":"file","size":42,"mode":384,"uid":1000,"gid":1000}],"complete":true}
```

Listing is bytewise sorted and uses metadata without following entry symlinks.
The `mode` value is an integer containing permission/special bits (384 = 0600).
`uid` and `gid` report numeric filesystem ownership; they do not imply authentication.
Control characters are JSON-escaped to prevent terminal control sequences in
listing output. Invalid UTF-8 displays as replacement characters; `name_hex`
preserves exact POSIX filename bytes for a frontend that needs lossless access.
Metadata errors on entries set `complete:false` and yield a nonzero exit status.
Mutations return `{"ok":true}` or an `{"error":"..."}` object. A future frontend
should invoke the executable with an argument array, never a constructed shell
command. It must handle nonzero exit status, not just parse stdout.

## Read-only Windows filesystem access

Linux's upstream FAT, exFAT and NTFS3 drivers are built into the source-built
kernel. Attachment is explicit, at the existing `/mnt/data` mountpoint:

```text
attach /dev/vdb ro vfat
files list /mnt/data
detach
attach /dev/vdb ro exfat
detach
attach /dev/vdb ro ntfs3
files copy "/mnt/data/Windows Notes.txt" "/root/Imported notes.txt"
detach
```

Select the **actual filesystem-containing device or partition** and correct type;
these device names are examples. There is no automatic probing or formatting.
Windows formats can only be requested with `ro`; no write mode or force-mount
option is exposed. Mounts are `nosuid,nodev,noexec`. Ext4 keeps its previous
explicit read/write mode and its read-only `noload` mode. Back up real data before
trying development software on it.

This is file/filesystem interoperability, not Windows executable compatibility.
BitLocker decryption, EFS, hibernated/dirty NTFS recovery, alternate data streams,
Windows ACL translation and application document rendering are outside this step.
Do not disable Windows protection or force a dirty volume to mount to bypass an
error. Imported files under `/root` are temporary; use an attached persistent ext4
volume for permanent storage (only one data mount is supported at a time).

## Verification

`make check` runs host-side tests without changing the target image;
`make target-check` tests the real musl-linked executables. Coverage includes quoted
and Unicode names, control/invalid filename bytes, no-overwrite behavior, symlink
refusal, FIFO/directory refusal, cleanup, explicit deletion and ELF packaging.

The five-case firmware matrix exercises the backend inside the guest. Additional
`python3 scripts/test-windows-filesystems.py` tests boot UEFI Q35 guests against
FAT32, exFAT and NTFS fixtures containing a filename with spaces and CRLF contents.
They list/read/import the file, verify write/delete refusal, and compare the whole
filesystem image SHA256 before and after. The emulator also exposes those fixtures
as read-only devices. Host filesystem utilities author test images only; none are
shipped in OminX. exFAT fixture seeding uses an isolated QEMU guest running a test-only initializer
and the source-built kernel. That initializer is never packaged into the product
image. No privileged host mounts are required.

The [recorded acceptance run](validation/files-and-storage.md) passed all 17 target
tests, five firmware configurations and all three Windows-filesystem cases.

## Next dependency gates

Before a graphical file-manager session: define unprivileged user/session ownership,
device permissions, and a display/input stack. Then source-build the selected Qt/KDE
libraries and integrate a graphical frontend over the tested file operations.
Do not substitute the legacy Debian desktop ISO for this independent target.
