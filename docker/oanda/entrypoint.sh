#!/bin/sh
# Same as the upstream image's own entrypoint (/opt/stick_oanda.sh) below,
# with a patch step inserted right before Apache starts serving. See
# Dockerfile for why.

# Heraldstick DOCKER stick_oanda.sh
# This script released under the terms of the GPL, version 2.0 or later.
# this is basically a heredoc for the config.web version of the O&A

# pre-setup, get the stuff you need from oanda.sca.org
wget --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36" -O /opt/my.cat "https://oanda.sca.org/my.cat"
wget --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36" -O /opt/config.web "https://oanda.sca.org/config.web"
wget --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36" -O /opt/oanda.db "https://oanda.sca.org/oanda.db"

DOCROOT=`grep ^DocumentRoot /usr/local/apache2/conf/httpd.conf | sed -e "s/\"//g" | cut -d\   -f 2`
echo DOCROOT IS $DOCROOT

rm $DOCROOT/index.html

echo  > HEREDOC
echo >> HEREDOC
echo >> HEREDOC
echo >> HEREDOC
echo localhost >> HEREDOC
echo 8080 >> HEREDOC
echo $DOCROOT >> HEREDOC
echo $DOCROOT >> HEREDOC
echo http://localhost:8080/>> HEREDOC
echo $DOCROOT/oanda.db >> HEREDOC
echo http://localhost:8080/oanda.db>> HEREDOC
echo $DOCROOT/my.cat >> HEREDOC
echo http://localhost:8080/my.cat>> HEREDOC
echo $DOCROOT/ordinary >> HEREDOC
echo http://localhost:8080/ordinary>> HEREDOC
echo $DOCROOT>> HEREDOC
echo http://localhost:8080/>> HEREDOC
echo >> HEREDOC
echo >> HEREDOC
echo >> HEREDOC
echo >> HEREDOC
echo >> HEREDOC
echo >> HEREDOC
perl /opt/config.web < HEREDOC
perl /mk_cat_file -i /opt/my.cat -o /mycat.pl
perl /opt/configdb << EOF





/opt/my.cat
/opt/oanda.db
/oanda_server.pl

n
EOF
echo Options +ExecCGI > /usr/local/apache2/htdocs/.htaccess

# --- patch: fix bugs in the generated CGI toolchain ---
# oanda_complex.cgi ships with a stray duplicate closing brace right
# before its trailing "# end of ..." comment (Perl syntax error).
perl -0777 -pi -e 's/\}\n\n\}\n# end of/}\n# end of/' /usr/local/apache2/htdocs/oanda_complex.cgi
perl -c /usr/local/apache2/htdocs/oanda_complex.cgi || exit 1
# common.pl requires mycat.pl from a path this image never creates; the
# real file lands at /mycat.pl.
mkdir -p /heralds/oanda.sca.org
ln -sf /mycat.pl /heralds/oanda.sca.org/mycat.pl
# --- end patch ---
apachectl start
/oanda_server.pl
