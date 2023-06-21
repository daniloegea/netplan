/*
 * Copyright (C) 2023 Canonical, Ltd.
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

#include <glib.h>
#include <glib/gstdio.h>
#include <glib-object.h>
#include <gio/gio.h>

#include "util.h"
#include "util-internal.h"
#include "parse.h"
#include "names.h"
#include "networkd.h"
#include "nm.h"
#include "openvswitch.h"
#include "sriov.h"
#include "netplan.h"
#include "parse-nm.h"

static gchar* rootdir;
static gchar* keyfile_path;

static GOptionEntry options[] = {
    {"root-dir", 'r', 0, G_OPTION_ARG_FILENAME, &rootdir, "Search for and generate configuration files in this root directory instead of /"},
    {"keyfile", 'k', 0, G_OPTION_ARG_FILENAME, &keyfile_path, "The Network Manager keyfile to be loaded into the current Netplan state"},
    {NULL}
};

int main(int argc, char** argv)
{
    NetplanError* error = NULL;
    GOptionContext* opt_context;
    int error_code = 0;
    NetplanParser* npp = NULL;
    NetplanParser* keyfile_npp = NULL;
    NetplanState* np_state = NULL;

    /* Parse CLI options */
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
        printf("Keyfile is mandatory\n");
        return 1;
    }

    keyfile_npp = netplan_parser_new();

    netplan_parser_load_keyfile(keyfile_npp, keyfile_path, &error);

    if (error) {
        printf("load keyfile error\n");
        goto cleanup;
    }

    if (g_hash_table_size(keyfile_npp->parsed_defs) == 0)
        goto cleanup;

    GHashTableIter iter;
    gpointer key, value;

    g_hash_table_iter_init(&iter, keyfile_npp->parsed_defs);
    g_hash_table_iter_next(&iter, &key, &value);
    NetplanNetDefinition* keyfile_netdef = value;
 
    npp = netplan_parser_new();
    netplan_parser_load_yaml_hierarchy(npp, rootdir, &error);

    if (error) {
        printf("load yaml hierarchy error\n");
        goto cleanup;
    }

    netplan_parser_load_keyfile(npp, keyfile_path, &error);

    if (error) {
        printf("load keyfile again error\n");
        goto cleanup;
    }

    NetplanNetDefinition* netdef = g_hash_table_lookup(npp->parsed_defs, keyfile_netdef->id);


    g_hash_table_iter_init(&iter, npp->parsed_defs);
    while (g_hash_table_iter_next(&iter, &key, &value)) {
        NetplanNetDefinition* n = value;

        if (n->bond) {
            if (g_strcmp0(n->bond, netdef->id)) {
                n->bond_link = netdef;
            }
        }

    }

    np_state = netplan_state_new();
    netplan_state_import_parser_results(np_state, npp, &error);

    netplan_state_update_yaml_hierarchy(np_state, "70-filename.yaml", rootdir, &error);

cleanup:
    g_option_context_free(opt_context);
    if (error)
        g_error_free(error);
    if (npp)
        netplan_parser_clear(&npp);
    if (np_state)
        netplan_state_clear(&np_state);
    return error_code;
}
