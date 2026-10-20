CC = $(CURDIR)/build/toolchain/bin/x86_64-linux-musl-gcc
HOSTCC = cc
CFLAGS = -O2 -Wall -Wextra -Werror

.PHONY: all check target-check build toolchain initramfs run media boot-check legacy-check legacy-build
all: build
toolchain:
	./scripts/build-toolchain.sh
build:
	./build.sh
build/ominx: src/core/ominx.c
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $<
initramfs: build/ominx scripts/make-initramfs.py
	python3 scripts/make-initramfs.py build/ominx build/initramfs.cpio.gz
build/host/ominx: src/core/ominx.c
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $<
check: build/host/ominx
	OMINX_TEST_BINARY=$(CURDIR)/build/host/ominx python3 -m unittest discover -s tests -v
target-check: initramfs
	OMINX_TEST_BINARY=$(CURDIR)/build/ominx python3 -m unittest discover -s tests -v
media:
	./scripts/build-media.sh
run:
	@test -f build/ominx-x86_64.iso || (echo 'Run make toolchain build first'; exit 1)
	qemu-system-x86_64 -m 512 -cdrom build/ominx-x86_64.iso -boot d -serial stdio -nic none
boot-check:
	python3 scripts/test-platforms.py
legacy-check:
	./scripts/check-config.sh
legacy-build:
	./scripts/build-debian-legacy.sh
