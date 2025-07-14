FROM debian:latest

# Use baseimage-docker's init system.
CMD ["/sbin/my_init"]

# Install updates
RUN apt-get update
RUN apt-get -y dist-upgrade
RUN apt-get install -y wget curl supervisor

# Install OLA dependencies
RUN apt-get install -y git-core
RUN apt-get install -y build-essential

# Download ola development files
RUN apt-get update
RUN apt-get install -y libcppunit-dev libcppunit-1.15-0 uuid-dev pkg-config libncurses5-dev libtool autoconf \
automake  g++ libmicrohttpd-dev  libmicrohttpd12 protobuf-compiler libprotobuf-lite23 libprotobuf-dev \
libprotoc-dev zlib1g-dev bison flex make libftdi-dev  libftdi1 libusb-1.0-0-dev liblo-dev \
libavahi-client-dev doxygen graphviz flake8 python3-protobuf

WORKDIR /tmp
RUN git clone https://github.com/OpenLightingProject/ola.git ola-dev
WORKDIR /tmp/ola-dev
RUN autoreconf -i

RUN ./configure --disable-all-plugins --enable-nanoleaf --enable-openpixelcontrol --enable-opendmx --enable-e131 --enable-espnet --enable-artnet --enable-dummy --enable-libftdi --enable-libusb --disable-uart --disable-osc --enable-usbpro --enable-usbdmx --enable-ftdidmx --disable-root-check --enable-python-libs
RUN make
RUN make install
RUN ldconfig
WORKDIR /

# Install avahi pieces required
RUN mkdir -p /var/run/dbus
##VOLUME /var/run/dbus
RUN apt-get update -y
RUN DEBIAN_FRONTEND=noninteractive apt-get -qq install -y avahi-daemon avahi-utils \
  && apt-get -qq -y autoclean \
  && apt-get -qq -y autoremove \
  && apt-get -qq -y clean
COPY avahi-daemon.conf /etc/avahi/avahi-daemon.conf

# Setup services
COPY supervisord.conf /etc/supervisor/supervisord.conf
RUN mkdir -p /var/log/supervisord
EXPOSE 9090
# Clean up APT when done.
RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
CMD supervisord -c /etc/supervisor/supervisord.conf
