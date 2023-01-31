#!/bin/bash

set -e
set -x

BUILDDIR="_leakcheckbuild"

meson setup ${BUILDDIR} -Db_sanitize=address,undefined
meson compile -C ${BUILDDIR} --verbose

TESTS=$(find ${BUILDDIR}/tests/ctests/ -executable -type f)
for test in ${TESTS}
do
    ./${test}
done

mkdir -p ${BUILDDIR}/fakeroot/{etc/netplan,run}
export LD_LIBRARY_PATH="${BUILDDIR}/src"

for yaml in examples/*.yaml
do
    chmod 600 ${yaml}
    cp ${yaml} ${BUILDDIR}/fakeroot/etc/netplan/
    ./${BUILDDIR}/src/generate --root-dir ${BUILDDIR}/fakeroot
    rm ${BUILDDIR}/fakeroot/etc/netplan/${yaml##*/}
done
