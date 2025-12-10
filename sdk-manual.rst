|

.. image:: images/simaai_logo.png
     :align: center

|

###################################################
SiMa.ai *eLxr* Software Development Kit(SDK) Manual
###################################################

|

.. epigraph:: This is a user-guide on SiMa.ai *eLxr* Board Support Package(BSP)

|

*********************
About *eLxr* Project
*********************

|

.. tip::  The *eLxr* project is a community-driven effort dedicated to broadening access to cutting-edge technologies for both enthusiasts and enterprise users seeking reliable and innovative solutions that scale from edge to cloud. The project produces and maintains an open source, enterprise-grade Debian-derivative distribution called eLxr that is easy for users to adopt and that fully honors the open source philosophy.

    The *eLxr* project’s mission is centered on accessibility, innovation, and maintaining the integrity of open source software. Making these advancements in an enterprise-grade Debian-derivative ensures that users benefit from a freely available Linux distribution.

    By emphasizing ease of adoption alongside open source principles, eLxr aims to attract a broad range of users and contributors who value both innovation and community-driven development, fostering collaboration and transparency and the spread of new technologies.

    The *eLxr* project is establishing a robust strategy for building on Debian’s ecosystem while also contributing back to it. Because “Debian citizens” contribute eLxr innovations and improvements upstream, they are actively participating in the community’s development activities. This approach not only enhances eLxr’s own distribution but also strengthens Debian by expanding its feature set and improving its overall quality.

    The ability to release technologies at various stages of Debian’s development lifecycle and to introduce innovative new content not yet available in Debian highlights eLxr’s agility and responsiveness to emerging needs. Moreover, the commitment to sustainability ensures that contributions made by eLxr members remain accessible and beneficial to the broader Debian community over the long term.[2]

|
|

***********
Terminology
***********
|

**MLSoC**: *Machine Learning System-on-Chip*

**SDK**: *Software Development Kit*

**BSP**: *Board Support Package*

**docker**: *A linux container* [3]

**platform**: *SiMa.ai MLSoC Name*

.. tip::
    * modalix
    * davinci


|
|

************
Assumptions
************
|

This manual assumes that **Ubuntu-22.04** host build machine is used and user is familiar with the basic Linux commands and environment.

The examples shown in this manual are using **modalix** platform however instructions can be applied on **davinci** platform with little or no modifications.

Furthermore, at the time of artifacts installation, it is assumed that,

* User has a SiMa.ai platform booted with an *eLxr* image and has root access
* The platform board is accessible from the Docker to copy the artifacts over
* The platform is booted with eMMC which is enumerated as mmcblk0 on Linux

|
|

*********************
SiMa.ai *eLxr* SDK
*********************
|


The *eLxr* build system is extended to build SiMa.ai Debian packages and images for SiMa.ai MLSoCs.

An SDK(a.k.a BSP) is provided for customers to build their software and install them on SiMa.ai MLSoC.

|

SDK Docker
""""""""""
|

Along with this manual, SiMa.ai SDK Dockerfiles(one for each platform) are provided to create the SDK docker container.

SDK docker contains all the toolchains/headers/libraries etc. needed to build the software for the SiMa.ai platform.

|

Building SDK Docker
"""""""""""""""""""

|

Prerequisite
============
|

- Install the docker engine on the host build machine[4]

- Install qemu-user-static package
    - ``sudo apt install qemu-user-static``

|

Build Docker Image
==================
|

- Build sdk docker image for the SiMa.ai platform(e.g. modalix)
    - ``docker build -t modalix-sdk --file Dockerfile.modalix .``

.. tip::
   A comma separated package list can be provided to install in the **sysroot** during docker build e.g.

   * ``docker build --build-arg SDK_PKG_LIST=libzix-dev,vxi-dev -t modalix-sdk --file Dockerfile.modalix .``

|

  .. code-block:: javascript

    $ docker image list
    REPOSITORY    TAG       IMAGE ID       CREATED       SIZE
    modalix-sdk   latest    5b692872f17f   3 hours ago   6.85GB

|

Launching SDK Docker
""""""""""""""""""""
|

- ``docker run -it --privileged -v $(pwd):/data -w /data -v /dev:/dev --pid=host modalix-sdk``

.. tip::
   * The sysroot is setup under ``/opt/toolchain/aarch64/<platform>`` directory

   * Though the build environment is automatically set at the docker launch, it can also be set manually e.g.
        * ``source /opt/bin/simaai-init-build-env <platform>``

|

|

****************
Build Software
****************
|

Linux Kernel
""""""""""""
|

Fetching kernel source
======================
|

- ``git clone https://github.com/SiMa-ai/simaai-linux.git && cd simaai-linux``

|

Configuring kernel
======================
|

- ``make ARCH=arm64 <platform-defconfig>``

.. tip::
   * platform-defconfig
       * simaai_modalix_defconfig
       * simaai_davinci_defconfig

.. code-block:: javascript

   root@83a273303643:/data/simaai-linux# make ARCH=arm64 simaai_modalix_defconfig
   ...
   ...
   #
   # configuration written to .config
   #

|

Building Kernel
======================
|

- ``make all -j8 ARCH=arm64 LOCALVERSION="-modalix" DTC_FLAGS=-@``

.. tip::
   * kernel image: ``arch/arm64/boot/Image``
   * device tree: ``arch/arm64/boot/dts/simaai/*.dtb``

.. code-block:: javascript

   root@83a273303643:/data/simaai-linux# make all -j8 ARCH=arm64 LOCALVERSION="-modalix" DTC_FLAGS=-@
   ...
   ...
   NM      System.map
   SORTTAB vmlinux
   OBJCOPY arch/arm64/boot/Image
   GZIP    arch/arm64/boot/Image.gz

|

Overlay Device tree
"""""""""""""""""""
|

- Create the device tree overlay file(dtso)

- Build the overlay devicetree blob(dtbo)
  - dtc -@ -I dts -O dtb -o <dtbo-name> <dtso-name>

.. code-block:: javascript

   root@83a273303643:/data# dtc -@ -I dts -O dtb -o imx415.dtbo imx415.dtso
|

U-boot
"""""""
|

Fetching u-boot source
======================
|

- ``git clone https://github.com/SiMa-ai/sima-ai-uboot.git && cd sima-ai-uboot``

|

Configuring u-boot
===================
|

- ``make ARCH=arm64 <platform-defconfig>``

.. tip::
   - platform-defconfig
       * simaai_modalix_debug_defconfig
       * sima_davinci-a65_defconfig

.. code-block:: javascript

   root@83a273303643:/data/sima-ai-uboot# make ARCH=arm64 simaai_modalix_debug_defconfig
   ...
   ...
   #
   # configuration written to .config
   #

|

Building u-boot
================
|

- ``make all u-boot-initial-env V=1``

.. tip::
   * u-boot image: ``u-boot.bin``

.. code-block:: javascript

   root@83a273303643:/data/sima-ai-uboot# make all u-boot-initial-env V=1
   ...
   ...
   make -f ./scripts/Makefile.build obj=tools ./tools/printinitialenv
   cc -Wp,-MD,tools/.printinitialenv.d -Wall -Wstrict-prototypes -O2 -fomit-frame-pointer   -
   std=gnu11   -DCONFIG_FIT_SIGNATURE -DCONFIG_FIT_SIGNATURE_MAX_SIZE=0xffffffff -
   DCONFIG_FIT_CIPHER -include ./include/compiler.h -idirafterinclude -
   idirafter./arch/arm/include -idirafter./dts/upstream/include -I./scripts/dtc/libfdt -
   I./tools -DUSE_HOSTCC -D__KERNEL_STRICT_NAMES -D_GNU_SOURCE    -o tools/printinitialenv
   tools/printinitialenv.c
  ./tools/printinitialenv | sed -e '/^\s*$/d' | sort -t '=' -k 1,1 -s -o u-boot-initial-env

|
|

******************
Install Artifacts
******************
|

List of artifacts

* U-boot Image
* Linux Kernel Image
* Linux Device Trees
* Linux Device Tree Overlays
* Linux Kernel Modules

.. tip::
   eMMC has 4 partitions:
    * ``mmcblk0p1`` : u-boot primary
    * ``mmcblk0p2`` : u-boot backup
    * ``mmcblk0p3`` : boot partition
    * ``mmcblk0p4`` : rootfs partition

   Partition3(``mmcblk0p3``) has two boot directories ``boot-0`` and ``boot-1``. One is primary and one for backup.

|

Copying u-boot
""""""""""""""
|

* Secure copy u-boot onto the board from docker

.. code-block:: javascript

   root@83a273303643:/data# pwd
   /data
   root@83a273303643:/data# scp sima-ai-uboot/u-boot.bin root@192.168.90.139:/tmp/
   root@192.168.90.139's password: 
   u-boot.bin                                                            100% 1024KB      6.9MB/s   00:00    


* Identify the u-boot partition currently in use on the board
    * ``parted /dev/mmcblk0 print | grep legacy_boot | cut -f2 -d" "``

.. code-block:: bash

   root@modalix:~# parted /dev/mmcblk0 print | grep legacy_boot | cut -f2 -d" "
   1

* Flash the new ``u-boot.bin`` to the currently used u-boot partition

.. code-block:: bash

   root@modalix:~# dd if=/tmp/u-boot.bin of=/dev/mmcblk0p1 status=progress
   2047+1 records in
   2047+1 records out
   1048560 bytes (1.0 MB, 1.0 MiB) copied, 0.0944332 s, 11.1 MB/s
   root@modalix:~# sync

|

Copying Kernel
""""""""""""""
|

* Figure the current boot directory on boot partition
    * ``strings /boot/uboot.env | grep boot_path= | cut -f2 -d"="``

.. code-block:: bash

   root@modalix:~# strings /boot/uboot.env | grep boot_path= | cut -f2 -d"="
   /boot-0/

|

Linux Kernel
===============
|

* copy new kernel image to the boot directory(/boot/<boot directory>)

.. code-block:: javascript

   root@83a273303643:/data# scp simaai-linux/arch/arm64/boot/Image root@192.168.90.139:/boot/boot-0/
   root@192.168.90.139's password: 
   Image

|

Device trees
============
|

* copy kernel device trees to the boot directory(/boot/<boot directory>)

.. code-block:: javascript

   root@83a273303643:/data# scp simaai-linux/arch/arm64/boot/dts/simaai/modalix*.dtb root@192.168.90.139:/boot/boot-0/
   root@192.168.90.139's password: 
   modalix-dvt.dtb                                                       100%  110KB     1.6MB/s   00:00    
   modalix-emulation-bench.dtb                                           100%  107KB   3.1MB/s   00:00    
   modalix-hhhl.dtb                                                      100%  110KB   4.1MB/s   00:00    
   modalix-som.dtb                                                       100%  108KB   3.2MB/s   00:00    
   modalix-vdk.dtb                                                       100%  108KB   3.6MB/s   00:00    


|

Device Tree Overlays
====================
|

* copy kernel device tree overlays to the boot directory(/boot/<boot directory>)

.. code-block:: javascript

   root@83a273303643:/data# scp imx415.dtbo root@192.168.90.139:/boot/boot-0/
   root@192.168.90.139's password: 
   imx415.dtbo                                                        100%  895    41.9KB/s   00:00

|

Kernel Modules
===============
|

* copy required kernel modules to their respective rootfs partition's modules directory(/lib/modules/<*kernel version string*>/kernel/..)
* ``uname -a`` command shows the kernel version string

.. code-block:: javascript

   root@83a273303643:/data# scp simaai-linux/drivers/net/phy/marvell10g.ko root@192.168.90.139:/lib/modules/6.1.22-modalix/kernel/drivers/net/phy/
   root@192.168.90.139's password: 
   marvell10g.ko                                                         100%   24KB 722.7KB/s   00:00 

|

Post Install
""""""""""""""
|

* depmod -a <*kernel version string*>
* sync
* reboot

.. code-block:: bash

   root@modalix:~# depmod -a 6.1.22-modalix
   root@modalix:~# sync
   root@modalix:~# reboot

* If new overlays are added
    * break into uboot prompt and add the new overlays in *dtbos* variable and save the environment
    * boot the platform

.. code-block:: bash

   Hit any key to stop autoboot:  0
   sima$ env set dtbos $dtbos imx415.dtbo
   sima$ saveenv
   Saving Environment to FAT... OK
   sima$ boot

|

|

******************
References
******************
|

[1]: https://elxr.org/about

[2]: https://www.windriver.com/blog/Introducing-eLxr

[3]: https://www.docker.com/

[4]: https://docs.docker.com/engine/install/ubuntu/
