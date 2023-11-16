/*
 * Copyright (C) 2024 Canonical, Ltd.
 * Author: Danilo Egea Gondolfo <danilo.egea.gondolfo@canonical.com>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; version 3.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include <stdlib.h>
#include <string.h>
#include <glob.h>
#include <unistd.h>
#include <errno.h>
#include <net/if.h>

#include <glib.h>
#include <glib/gstdio.h>

#include <seccomp.h>

#include "types.h"
#include "parse.h"
#include "netplan.h"
#include "parse-nm.h"
#include "util.h"

static gchar* rootdir = NULL;
static gchar* keyfile_path = NULL;
static gboolean delete = FALSE;

static GOptionEntry options[] = {
    {"root-dir", 'r', 0, G_OPTION_ARG_FILENAME, &rootdir, "Search for and generate configuration files in this root directory instead of /", NULL},
    {"keyfile", 'k', 0, G_OPTION_ARG_FILENAME, &keyfile_path, "The Network Manager keyfile to be loaded into the current Netplan state", "<.nmconnection file path>"},
    {"delete", 'd', 0, G_OPTION_ARG_NONE, &delete, "Delete a connection", NULL},
    {NULL}
};

static int load_keyfile(const gchar* kf_path, const gchar* root_dir, gchar** output_keyfile);
static int delete_connection(const gchar* kf_path, const gchar* root_dir);

static void setup_seccomp(void);

int
main(int argc, char** argv)
{
    NetplanError* error = NULL;
    GOptionContext* opt_context;
    int error_code = 0;

    setup_seccomp();

    opt_context = g_option_context_new(NULL);
    g_option_context_set_summary(opt_context, "Generate backend network configuration from netplan YAML definition.");
    g_option_context_set_description(opt_context,
                                     "This program reads the specified netplan YAML definition file(s)\n"
                                     "or, if none are given, /etc/netplan/*.yaml.\n"
                                     "It then generates the corresponding systemd-networkd, NetworkManager,\n"
                                     "and udev configuration files in /run.");
    g_option_context_add_main_entries(opt_context, options, NULL);

    if (!g_option_context_parse(opt_context, &argc, &argv, &error)) {
        fprintf(stderr, "failed to parse options: %s\n", error->message);
        return 1;
    }

    if (!keyfile_path) {
        fprintf(stderr, "Keyfile is mandatory\n");
        return 1;
    }

    if (delete) {
        error_code = delete_connection(keyfile_path, rootdir);
    } else {
        gchar* output_keyfile = NULL;

        error_code = load_keyfile(keyfile_path, rootdir, &output_keyfile);

        if (!error_code) {
            fprintf(stdout, "%s", output_keyfile);
            g_free(output_keyfile);
        }
    }

    return error_code;
}

static void
setup_seccomp(void)
{
    int syscalls_allowlist[] = {
        SCMP_SYS(write),
        SCMP_SYS(futex),
        SCMP_SYS(openat),
        SCMP_SYS(newfstatat),
        SCMP_SYS(close),
        SCMP_SYS(read),
        SCMP_SYS(fcntl),
        SCMP_SYS(access),
        SCMP_SYS(mkdir),
        SCMP_SYS(exit_group),
        SCMP_SYS(getpid),
        SCMP_SYS(lseek),
        SCMP_SYS(umask),
        SCMP_SYS(getdents64),
        SCMP_SYS(brk),
        SCMP_SYS(memfd_create),
        SCMP_SYS(dup),
        SCMP_SYS(unlink),
    };
    scmp_filter_ctx ctx;
    ctx = seccomp_init(SCMP_ACT_ERRNO(EPERM));

    for(unsigned long i = 0 ; i < sizeof(syscalls_allowlist) / sizeof(int); i++)
        seccomp_rule_add(ctx, SCMP_ACT_ALLOW, syscalls_allowlist[i], 0);

    seccomp_load(ctx);
    seccomp_release(ctx);
}

static gboolean
load_keyfile(const gchar* kf_path, const gchar* root_dir, gchar** output_keyfile)
{
    NetplanError* error = NULL;
    NetplanParser* npp = NULL;
    NetplanState* np_state = NULL;
    NetplanNetDefinition* netdef = NULL;
    NetplanStateIterator state_iter;
    g_autofree gchar *escaped_ssid = NULL;
    g_autofree gchar *ssid = NULL;
    g_autoptr(GKeyFile) kf = NULL;
    gchar* path;
    ssize_t path_size;
    int error_code = 0;

    npp = netplan_parser_new();

    if (!npp) {
        fprintf(stderr, "Failed to create the parser\n");
        goto cleanup;
    }

    netplan_parser_load_keyfile(npp, kf_path, &error);

    if (error) {
        fprintf(stderr, "load keyfile again error\n");
        goto cleanup;
    }

    np_state = netplan_state_new();
    netplan_state_import_parser_results(np_state, npp, &error);

    netplan_state_iterator_init(np_state, &state_iter);
    /* At this point we have a single netdef in the netplan state */
    netdef = netplan_state_iterator_next(&state_iter);

    if (!netdef) {
        fprintf(stderr, "Cannot find a netdef\n");
        goto cleanup;
    }

    if (!netplan_netdef_write_yaml(np_state, netdef, root_dir, &error)) {
        fprintf(stderr, "Cannot write yaml\n");
        goto cleanup;
    }

    kf = g_key_file_new();
    if (!g_key_file_load_from_file(kf, keyfile_path, G_KEY_FILE_NONE, &error)) {
        g_warning("netplan: cannot load keyfile");
        return FALSE;
    }
    ssid = g_key_file_get_string(kf, "wifi", "ssid", NULL);
    escaped_ssid = ssid ? g_uri_escape_string(ssid, NULL, TRUE) : NULL;

    /* Determine the output file name */

    // Calculating the maximum space needed to store the new keyfile path
    // give some extra buffer, e.g. when going from  ConName to ConName.nmconnection + uuid
    path_size = strlen(keyfile_path) + IF_NAMESIZE + 100;
    if (escaped_ssid)
        path_size += strlen(escaped_ssid);
    path = g_malloc0(path_size);
    path_size = netplan_netdef_get_output_filename(netdef, ssid, path, path_size);

    if (path_size < 0) {
        error_code = FALSE;
        goto cleanup;
    }

    *output_keyfile = path;

cleanup:
    if (error)
        g_error_free(error);
    if (npp)
        netplan_parser_clear(&npp);
    if (np_state)
        netplan_state_clear(&np_state);
    return error_code;
}

static gboolean
delete_connection(const gchar* keyfile_path, const gchar* root_dir)
{
    g_autoptr(GKeyFile) kf;
    g_autofree gchar* ssid = NULL;
    g_autofree gchar *netplan_id = NULL;
    ssize_t netplan_id_size;

    kf = g_key_file_new();
    if (!g_key_file_load_from_file(kf, keyfile_path, G_KEY_FILE_NONE, NULL))
        return FALSE;

    ssid = g_key_file_get_string(kf, "wifi", "ssid", NULL);

    netplan_id = g_malloc0(strlen(keyfile_path));
    netplan_id_size = netplan_get_id_from_nm_filepath(keyfile_path, ssid, netplan_id, strlen(keyfile_path) - 1);
    if (netplan_id_size > 0) {
        return netplan_delete_connection(netplan_id, root_dir);
    }
    return FALSE;
}
