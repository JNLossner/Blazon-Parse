FROM ltanzos/oanda:latest

# Upstream's CMD (/opt/stick_oanda.sh) downloads its CGI toolchain fresh
# from https://oanda.sca.org on every container start and generates
# oanda_complex.cgi/common.pl from it. That generated code currently ships
# two bugs that break every search:
#  - oanda_complex.cgi has a stray duplicate "}" (Perl syntax error).
#  - common.pl requires mycat.pl from /heralds/oanda.sca.org/, a path this
#    image never creates; the real file lands at /mycat.pl.
# entrypoint.sh is stick_oanda.sh with a patch step inserted right before
# Apache starts serving, so the fix applies to the freshly generated files
# every time the container starts.
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

CMD ["/bin/sh", "/opt/entrypoint.sh"]
