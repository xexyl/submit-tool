#!/usr/bin/env make
#
# iocccsubmit - IOCCC submit server tool
#
# Copyright (c) 2024 by Landon Curt Noll.  All Rights Reserved.
#
# Permission to use, copy, modify, and distribute this software and
# its documentation for any purpose and without fee is hereby granted,
# provided that the above copyright, this permission notice and text
# this comment, and the disclaimer below appear in all of the following:
#
#       supporting documentation
#       source copies
#       source works derived from this source
#       binaries derived from this source or from derived source
#
# LANDON CURT NOLL DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
# INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO
# EVENT SHALL LANDON CURT NOLL BE LIABLE FOR ANY SPECIAL, INDIRECT OR
# CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF
# USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
# OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.
#
# chongo (Landon Curt Noll, http://www.isthe.com/chongo/index.html) /\oo/\
#
# Share and enjoy! :-)

#############
# utilities #
#############

CHMOD= chmod
CMP= cmp
CP= cp
ID= id
INSTALL= install
MKDIR= mkdir
PYTHON= python3
RM= rm
SED= sed
SHELL= bash

######################
# target information #
######################

# V=@:  do not echo debug statements (quiet mode)
# V=@   echo debug statements (debug / verbose mode)
#
V=@:
#V=@

# package version
#
VERSION= 0.2.1

# Python package name
#
PKG_NAME= iocccsubmit

# Python package source
#
PKG_SRC= ${PKG_NAME}/__init__.py ${PKG_NAME}/ioccc.py ${PKG_NAME}/ioccc_common.py

# etc read-only directory source owned by root
#
ETC_RO_ROOT_SRC= etc/init.iocccpasswd.json etc/init.state.json etc/pw.words \
	etc/requirements.txt

# etc read-write directory source owned by root
#
ETC_RW_SRC= etc/iocccpasswd.lock etc/state.lock

# all etc src
#
ETC_SRC= ${ETC_RO_ROOT_SRC} ${ETC_RW_SRC}

# static directory source
#
STATIC_SRC= static/ioccc.css static/ioccc.js static/ioccc.png static/login-example.jpg \
	    static/favicon.ico static/robots.txt static/apple-touch-icon.png \
	    static/apple-touch-icon-precomposed.png

# templates directory source
#
TEMPLATES_SRC= templates/login.html templates/not-open.html templates/passwd.html \
	templates/submit.html

# wsgi code to install for apache to execute
#
WSGI_SRC= wsgi/ioccc.wsgi

# files to install under ${DOCROOT}
#
INSTALL_UNDER_DOCROOT= ${ETC_SRC} ${STATIC_SRC} ${TEMPLATES_SRC} ${WSGI_SRC}

# Apache document root directory where non-python python package files are installed under
# 
# We install ${INSTALL_UNDER_DOCROOT} files under this directory, sometimes in sub-directories.
#
DOCROOT= /var/www/ioccc

# executable scripts that are not part of the python module.
#
# Executable files to install under ${DESTDIR}.
#
# NOTE: bin/pychk.sh is only needed for testing and thus is not needed under ${DESTDIR}.
#
BIN_SRC= bin/genflaskkey.sh bin/ioccc_date.py bin/ioccc_passwd.py bin/set_slot_status.py

# Where to install programs that are not part of the python module.
#
# We install ${BIN_SRC} executables under this directory.
#
DESTDIR= /usr/local/bin

# what to build
#
TARGETS= dist/${PKG_NAME}-${VERSION}-py3-none-any.whl

######################################
# all - default rule - must be first #
######################################

all: ${TARGETS}

#################################################
# .PHONY list of rules that do not create files #
#################################################

.PHONY: all configure clean clobber nuke install \
	root_install revenv wheel venv_install

###############
# build rules #
###############

setup.cfg: setup.cfg.template etc/requirements.txt
	${V} echo DEBUG =-= $@ start =-=
	${RM} -f $@ tmp.requirements.txt.tmp
	${SED} -e 's/^/    /' < etc/requirements.txt > tmp.requirements.txt.tmp
	${SED} -e 's/@@VERSION@@/${VERSION}/' \
	       -e 's/@@PKG_NAME@@/${PKG_NAME}/' \
	       -e '/^install_requires =/ {' -e 'r tmp.requirements.txt.tmp' -e '}' \
		  < setup.cfg.template > $@
	${RM} -f tmp.requirements.txt.tmp
	${V} echo DEBUG =-= $@ end =-=

venv: etc/requirements.txt setup.cfg
	${V} echo DEBUG =-= $@ start =-=
	${RM} -rf venv __pycache__
	${PYTHON} -m venv venv
	# was: pip install --upgrade ...
	source ./venv/bin/activate && \
	    ${PYTHON} -m pip install --upgrade pylint pip setuptools wheel build && \
	    ${PYTHON} -m pip install -r etc/requirements.txt
	${V} echo DEBUG =-= $@ end =-=

build/lib/submittool: ${PKG_SRC} venv
	${V} echo DEBUG =-= $@ start =-=
	# was: python3 setup.py build
	source ./venv/bin/activate && \
	    ${PYTHON} -c 'import setuptools; setuptools.setup()' sdist
	${V} echo DEBUG =-= $@ end =-=

dist/${PKG_NAME}-${VERSION}-py3-none-any.whl: ${PKG_SRC} venv build/lib/submittool
	${V} echo DEBUG =-= $@ start =-=
	# was: python3 setup.py bdist_wheel
	source ./venv/bin/activate && \
	    ${PYTHON} -m build --sdist --wheel
	${V} echo DEBUG =-= $@ end =-=


#################
# utility rules #
#################

# wheel - make the python package wheel
#
wheel: dist/${PKG_NAME}-${VERSION}-py3-none-any.whl
	${V} echo DEBUG =-= $@ start =-=
	${V} echo DEBUG =-= $@ end =-=

# revenv - force to rebuild the python virtual environment
#
revenv:
	${V} echo DEBUG =-= $@ start =-=
	${RM} -rf venv __pycache__
	${PYTHON} -m venv venv
	# was: pip3 install --upgrade ...
	source ./venv/bin/activate && \
	    ${PYTHON} -m pip install --upgrade pylint pip setuptools wheel build && \
	    ${PYTHON} -m pip install -r etc/requirements.txt
	${V} echo DEBUG =-= $@ end =-=

# install the python package under the python virtual environment
#
venv_install: venv dist/${PKG_NAME}-${VERSION}-py3-none-any.whl
	${V} echo DEBUG =-= $@ start =-=
	# was: python3 setup.py install
	source ./venv/bin/activate && \
	    ${PYTHON} -m pip install .
	@echo 'Do not forget to:'
	@echo
	@echo '    source venv/bin/activate'
	@echo
	${V} echo DEBUG =-= $@ end =-=

###################################
# standard Makefile utility rules #
###################################

configure: setup.cfg
	${V} echo DEBUG =-= $@ start =-=
	${V} echo DEBUG =-= $@ end =-=

clean:
	${V} echo DEBUG =-= $@ start =-=
	${RM} -f tmp.requirements.txt.tmp
	${V} echo DEBUG =-= $@ end =-=

clobber: clean
	${V} echo DEBUG =-= $@ start =-=
	${RM} -rf venv __pycache__ ${PKG_NAME}/__pycache__
	${RM} -rf dist build ${PKG_NAME}.egg-info
	${RM} -f setup.cfg
	${V} echo DEBUG =-= $@ end =-=

# remove active working elements including users
#
nuke: clobber
	${V} echo DEBUG =-= $@ start =-=
	${RM} -rf users
	${V} echo DEBUG =-= $@ end =-=

install: venv_install
	${V} echo DEBUG =-= $@ start =-=
	@echo 'This only installed locally into a python virtual environment.'
	@echo 'To setup on the server under ${DOCROOT}, as root run:'
	@echo
	@echo '    make root_install'
	@echo
	${V} echo DEBUG =-= $@ end =-=

root_install: ${INSTALL_UNDER_DOCROOT} ${BIN_SRC} dist/${PKG_NAME}-${VERSION}-py3-none-any.whl
	${V} echo DEBUG =-= $@ start =-=
	@if [[ $$(${ID} -u) != 0 ]]; then echo "ERROR: must be root to $@"; exit 1; fi
	# was: python3 setup.py install
	${PYTHON} -m pip install --force-reinstall .
	${INSTALL} -o ioccc -g ioccc -m 0555 -d ${DOCROOT}
	${INSTALL} -o ioccc -g ioccc -m 0755 -d ${DOCROOT}/etc
	${INSTALL} -o ioccc -g ioccc -m 0444 ${ETC_RO_ROOT_SRC} ${DOCROOT}/etc
	${INSTALL} -o ioccc -g ioccc -m 0644 ${ETC_RW_SRC} ${DOCROOT}/etc
	${INSTALL} -o ioccc -g ioccc -m 0555 -d ${DOCROOT}/static
	${INSTALL} -o ioccc -g ioccc -m 0444 ${STATIC_SRC} ${DOCROOT}/static
	${INSTALL} -o ioccc -g ioccc -m 0555 -d ${DOCROOT}/templates
	${INSTALL} -o ioccc -g ioccc -m 0444 ${TEMPLATES_SRC} ${DOCROOT}/templates
	${INSTALL} -o ioccc -g ioccc -m 0755 -d ${DOCROOT}/users
	${INSTALL} -o ioccc -g ioccc -m 0755 -d ${DOCROOT}/wsgi
	${INSTALL} -o ioccc -g ioccc -m 0555 ${WSGI_SRC} ${DOCROOT}/wsgi
	${INSTALL} -o root -g root -m 0755 -d ${DESTDIR}
	${INSTALL} -o root -g root -m 0555 ${BIN_SRC} ${DESTDIR}
	${V} echo DEBUG =-= $@ end =-=
