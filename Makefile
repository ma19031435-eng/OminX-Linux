CC = cc
CFLAGS = -O2 -Wall -Wextra -Werror

.PHONY: all check build initramfs run legacy-check legacy-build
all: initramfs
build:
	./build.sh
build/ominx: src/core/ominx.c
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $<
initramfs: build/ominx scripts/make-initramfs.py
	python3 scripts/make-initramfs.py build/ominx build/initramfs.cpio.gz
check: initramfs
	python3 -m unittest discover -s tests -v
run:
	@test -f build/bzImage || (echo 'Build the kernel first; see README.md'; exit 1)
	qemu-system-x86_64 -m 256 -kernel build/bzImage -initrd build/initramfs.cpio.gz -append 'console=ttyS0 rdinit=/init panic=-1' -nographic -no-reboot -nic none
legacy-check:
	./scripts/check-config.sh
legacy-build:
	./scripts/build-debian-legacy.sh
