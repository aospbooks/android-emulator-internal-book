# Android Emulator Internals

## A Developer's Guide to the Android Emulator

---

**First Edition**

---

*A source-code-referenced exploration of the Android Emulator, from the host
virtual machine to the guest kernel.*

---

## Copyright

Copyright 2026. All rights reserved.

Self-published.

No part of this book may be reproduced, stored in a retrieval system, or
transmitted without the prior written permission of the author. This applies to
any form and any means: electronic, mechanical, photocopying, recording, or
otherwise. The exceptions are brief quotations in critical reviews and certain other
noncommercial uses that copyright law permits.

This book is based on analysis of the Android Emulator source code and the
upstream projects it builds on. These projects have a mix of licenses: the
Apache License, Version 2.0, the GNU General Public License (QEMU), and other
open-source licenses. All source code excerpts and file path references are used for
educational and commentary purposes.

Android is a trademark of Google LLC. QEMU is the work of the QEMU project and
its contributors. This book is not affiliated with, endorsed by, or sponsored by
Google LLC, the Android Open Source Project, or the QEMU project.

All source code references in this book correspond to the Android Emulator
`main` development tree as of mid-2026. File paths, line numbers, and code
excerpts may differ in past or future revisions of the source tree. The reader
is encouraged to verify references against their own checked-out source.

**Disclaimer**: The information in this book is provided on an "as is" basis,
without warranty. While every effort has been made to ensure accuracy through
direct source code verification, neither the author nor the publisher shall have
any liability to any person or entity with respect to any loss or damage caused
or alleged to be caused directly or indirectly by the information contained in
this book.

**Source tree baseline**: the Android Emulator `main`-branch superproject
(forked QEMU under `external/qemu`, `hardware/google/aemu`, and
`hardware/google/gfxstream`), synced mid-2026.

---

## Preface

### The Problem This Book Solves

Almost every Android developer launches the Android Emulator dozens of times a
day, yet few understand what happens after they press "play." It is not a thin
wrapper around a virtual machine. It is a large host program with many jobs.
It forks QEMU and plugs in a custom Android machine model. It emulates the
virtual hardware of an entire phone: sensors, a battery, a modem, cameras, and
Bluetooth.

The emulator also streams GPU commands out of the guest to a host renderer. It
exposes a gRPC and telnet control plane. It presents the result through a Qt
window or through a WebRTC video stream embedded in an IDE.

The official documentation explains how to *use* the emulator: how to create an
AVD, pass command-line flags, and forward ports. But if you need to understand
*how those features are implemented*, the questions are these.

For example, how does a sensor value set over gRPC reach the guest's sensor
HAL? How is a `glDrawArrays` call in an app encoded, shipped across a pipe, and replayed against the host GPU? How does
Quickboot snapshot the entire machine to disk and restore it in a second? How
does `adb` find an emulator with no network device? There is no single
source-referenced guide for these questions.

This book is that guide. Every architectural claim points at a specific file in
the emulator source tree and, where useful, a line. You can open the code and
read along.

### Who This Book Is For

- **Emulator and tools engineers** who need a map of an unfamiliar subsystem.
- **Platform and HAL developers** who debug guest behavior that only reproduces
  under emulation.
- **Graphics and virtualization engineers** who work on gfxstream, ANGLE, or the
  QEMU device model.
- **Curious Android developers** who want to know what the green "play" button
  actually does.

### How This Book Is Organized

The chapters move bottom-to-top through the stack. Part I orients you and covers
the build. Part II is the QEMU foundation and CPU acceleration. Part III is the
`android-emu` core. Part IV is the graphics pipeline. Parts V–VII cover media,
connectivity, and the user interfaces.

Part VIII follows the guest from system
image to boot. Part IX covers testing and debugging.

### A Note on Source References

The emulator is a moving target. Line numbers drift; files are renamed; whole
subsystems are rewritten between releases. Use the references here to find the
right *place* in the tree. They do not guarantee that line 412 still says what it
said when this was written. If you are not sure, use `grep`.
