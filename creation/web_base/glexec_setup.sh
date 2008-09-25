#!/bin/bash

############################################################
#
# This script will setup the gLExec parameters
#
############################################################

glidein_config=$1
tmp_fname=${glidein_config}.$$.tmp

# import add_config_line function
add_config_line_source=`grep '^ADD_CONFIG_LINE_SOURCE ' $glidein_config | awk '{print $2}'`
source $add_config_line_source

# --------------------------------------------------
# create a local copy of the shell
# gLExec does not like symlinks adn this way we are sure it is a file
cp -p /bin/sh ./sh
if [ $? -ne 0 ]; then
    echo "Failed to copy /bin/sh to . ($PWD)" 1>&2
    exit 1
fi
add_config_line "ALTERNATIVE_SHELL" "$PWD/sh" 


# --------------------------------------------------
# Set glidein working dir into the tmp dir
# This is needes since the user will be changed and 
# the tmo directory is world writtable
glide_tmp_dir=`grep '^TMP_DIR ' $glidein_config | awk '{print $2}'`
if [ -z "$glide_tmp_dir" ]; then
    echo "TMP_DIR not found!" 1>&2
    exit 1
fi
add_config_line "GLEXEC_USER_DIR" "$glide_tmp_dir"

# --------------------------------------------------
#
# Tell Condor to actually use gLExec
#
glexec_bin=`grep '^GLEXEC_BIN ' $glidein_config | awk '{print $2}'`
if [ -z "$glexec_bin" ]; then
    glexec_bin="OSG"
    echo "GLEXEC_BIN not found, using default '$glexec_bin'" 1>&2
fi

if [ "$glexec_bin" == "OSG" ]; then
    echo "GLEXEC_BIN was OSG, expand to '$OSG_GLEXEC_LOCATION'" 1>&2
    glexec_bin="$OSG_GLEXEC_LOCATION"
fi

# but first test it does exist

if [ -x "$glexec_bin" ]; then
    echo "Using gLExec binary '$glexec_bin'"
else
    echo "gLExec binary '$glexec_bin' not found!" 1>&2
    exit 1
fi


glexec_job=`grep '^GLEXEC_JOB ' $glidein_config | awk '{print $2}'`
if [ -z "$glexec_job" ]; then
    # default to the old mode
    glexec_job=False
fi

if [ "$glexec_job" == "True" ]; then
    add_config_line "GLEXEC_STARTER" "False"
    add_config_line "GLEXEC_JOB" "True"
else
    add_config_line "GLEXEC_STARTER" "True"
    add_config_line "GLEXEC_JOB" "False"
fi
add_config_line "GLEXEC_BIN" "$glexec_bin"

####################################################################
# Add requirement that only jobs with X509 attributes can start here
####################################################################

start_condition=`grep '^GLIDEIN_Entry_Start ' $glidein_config | awk '{print $2}'`
if [ -z "$start_condition" ]; then
    add_config_line "GLIDEIN_Entry_Start" "x509userproxysubject=!=UNDEFINED"
else
    add_config_line "GLIDEIN_Entry_Start" "(x509userproxysubject=!=UNDEFINED)&&($start_condition)"
fi

exit 0
