# Compiler-runtime notices

- `GCC-COPYING3` and `GCC-RUNTIME-EXCEPTION`: GCC upstream mirror
  `gcc-mirror/gcc`, tag `releases/gcc-14.3.0`, files `COPYING3` and `COPYING.RUNTIME`.
- `MUSL-COPYRIGHT`: musl mirror `ifduyue/musl`, tag `v1.2.6`, file `COPYRIGHT`.

These are notices for the existing source-built compiler runtime, not host
library inputs. Runtime binaries are copied only from the pinned GCC/musl
compiler prefix and audited along with the rest of the target dependency closure.
