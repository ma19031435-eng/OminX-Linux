CC = $(CURDIR)/build/toolchain/bin/x86_64-linux-musl-gcc
HOSTCC = cc
CFLAGS = -O2 -Wall -Wextra -Werror

.PHONY: all check target-check build toolchain initramfs run media boot-check legacy-check legacy-build
all: build
toolchain:
	./scripts/build-toolchain.sh
build:
	./build.sh
build/ominx: src/core/ominx.c src/lib/parse.c src/lib/files.c src/lib/parse.h src/lib/files.h src/lib/session.c src/lib/session.h src/lib/control.c src/lib/control.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-files: src/files/main.c src/lib/files.c src/lib/files.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-control: src/control/main.c src/lib/control.h src/lib/session.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-login: src/login/broker.c src/login/login.c src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-seat: src/login/seat.c src/lib/control.c src/lib/control.h src/lib/session.h src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-passwd: src/login/passwd.c src/login/login.c src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-login-probe: src/login/probe.c src/login/login.c src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
# Same source, target toolchain, service checks bypassed: runs the real musl crypt.
build/ominx-login-test: src/login/broker.c src/login/login.c src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -DOMINX_LOGIN_TEST -static -o $@ $(filter %.c,$^)
initramfs: build/ominx build/ominx-files build/ominx-control scripts/make-initramfs.py
	python3 scripts/make-initramfs.py build/ominx build/initramfs.cpio.gz build/ominx-files build/ominx-control
build/host/ominx: src/core/ominx.c src/lib/parse.c src/lib/files.c src/lib/parse.h src/lib/files.h src/lib/session.c src/lib/session.h src/lib/control.c src/lib/control.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/host/ominx-files: src/files/main.c src/lib/files.c src/lib/files.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/host/ominx-control: src/control/main.c src/lib/control.h src/lib/session.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/host/ominx-login-test: src/login/broker.c src/login/login.c src/login/login.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -DOMINX_LOGIN_TEST -static -o $@ $(filter %.c,$^) -lcrypt
build/host/ominx-passwd: src/login/passwd.c src/login/login.c src/login/login.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^) -lcrypt
check: build/host/ominx build/host/ominx-files build/host/ominx-control build/host/ominx-login-test build/host/ominx-passwd
	OMINX_CONTROL_BINARY=$(CURDIR)/build/host/ominx-control OMINX_FILES_BINARY=$(CURDIR)/build/host/ominx-files OMINX_TEST_BINARY=$(CURDIR)/build/host/ominx python3 -m unittest discover -s tests -v
target-check: initramfs build/ominx-login build/ominx-seat build/ominx-passwd build/ominx-login-probe build/ominx-login-test
	OMINX_CONTROL_BINARY=$(CURDIR)/build/ominx-control OMINX_FILES_BINARY=$(CURDIR)/build/ominx-files OMINX_TEST_BINARY=$(CURDIR)/build/ominx OMINX_LOGIN_BINARY=$(CURDIR)/build/ominx-login-test OMINX_PASSWD_BINARY=$(CURDIR)/build/ominx-passwd python3 -m unittest discover -s tests -v
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
