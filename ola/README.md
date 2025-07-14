# Docker container for Open Lighting Architecture

This docker image contains
DBUS Daemon
AVAHI
OLA (Compiled from source) - https://www.openlighting.org/ola/linuxinstall/#Git

Some of the plugins have been disabled for initial build, I will probably re-add as required.

Interactive running command
docker run  --net=host --rm -t -i ola /sbin/my_init -- bash -l

Background running command
docker run  --net=host -p 9090 -t -d docker-ola
