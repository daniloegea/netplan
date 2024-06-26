---
title: NETPLAN-GENERATE
section: 8
author:
- Daniel Axtens (<daniel.axtens@canonical.com>)
...

## NAME

`netplan-generate` - generate back-end configuration from Netplan YAML files

## SYNOPSIS

  **`netplan`** \[*--debug*\] **generate** **-h**|**--help**

  **`netplan`** \[*--debug*\] **generate** \[*--root-dir ROOT_DIR*\] \[*--mapping MAPPING*\]

## DESCRIPTION

**`netplan generate`** converts Netplan YAML into configuration files
understood by the back ends (**`systemd-networkd`**(8) or
**`NetworkManager`**(8)). It *does not* apply the generated
configuration.

You will not normally need to run this directly as it is run by
**`netplan apply`**, **`netplan try`**, or at boot.

Only if executed during the systemd `initializing` phase
(i.e. "Early boot, before `basic.target` is reached"), will
it attempt to start/apply the newly created service units.
**Requires feature: `generate-just-in-time*`*

When called as a systemd.generator(7), all the parsing and validation errors
will be ignored by default. If network definitions are skipped due to
parsing errors, they might be incomplete. That means that the
back end configuration emitted might not be fully valid.

For details of the configuration file format, see **`netplan`**(5).

## OPTIONS

`-h`, `--help`
:    Print basic help.

`--debug`
:    Print debugging output during the process.

`--root-dir` *`ROOT_DIR`*
:   Instead of looking in `/{lib,etc,run}/netplan`, look in
    `/ROOT_DIR/{lib,etc,run}/netplan`.

`--mapping` *`MAPPING`*
:   Instead of generating output files, parse the configuration files
    and print some internal information about the device specified in
    *`MAPPING`*.

## HANDLING MULTIPLE FILES

There are 3 locations that **`netplan generate`** considers:

 * `/lib/netplan/*.yaml`
 * `/etc/netplan/*.yaml`
 * `/run/netplan/*.yaml`

If there are multiple files with exactly the same name, then only one
will be read. A file in `/run/netplan` will shadow (completely replace)
a file with the same name in `/etc/netplan`. A file in `/etc/netplan`
will itself shadow a file in `/lib/netplan`.

Or, in other words, `/run/netplan` is top priority, then `/etc/netplan`,
with `/lib/netplan` having the lowest priority.

If there are files with different names, then they are considered in
lexicographical order - regardless of the directory they are in. Later
files add to or override earlier files. For example,
`/run/netplan/10-xyz.yaml` would be updated by `/lib/netplan/20-abc.yaml`.

If you have two files with the same key/setting, the following rules
apply:

 * If the values are YAML boolean or scalar values (numbers and
   strings) the old value is overwritten by the new value.

 * If the values are sequences, the sequences are concatenated - the
   new values are appended to the old list.

 * If the values are mappings, Netplan will examine the elements
   of the mappings in turn using these rules.

## SEE ALSO

  **`netplan`**(5), **`netplan-apply`**(8), **`netplan-try`**(8),
  **`systemd-networkd`**(8), **`NetworkManager`**(8)
