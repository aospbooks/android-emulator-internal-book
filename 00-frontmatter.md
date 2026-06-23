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
transmitted in any form or by any means — electronic, mechanical, photocopying,
recording, or otherwise — without the prior written permission of the author,
except for brief quotations embedded in critical reviews and certain other
noncommercial uses permitted by copyright law.

This book is based on analysis of the Android Emulator source code and the
upstream projects it builds on, which are licensed under a mix of the Apache
License, Version 2.0, the GNU General Public License (QEMU), and other
open-source licenses. All source code excerpts and file path references are used
for educational and commentary purposes.

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

The Android Emulator is the tool almost every Android developer launches dozens
of times a day, yet few understand what happens after they press "play." It is
not a thin wrapper around a virtual machine. It is a large host program that
forks QEMU, plugs in a custom Android machine model, emulates an entire phone's
worth of virtual hardware — sensors, a battery, a modem, cameras, Bluetooth —
streams GPU commands out of the guest to a host renderer, exposes a gRPC and
telnet control plane, and presents the result through either a Qt window or a
WebRTC video stream embedded in an IDE.

The official documentation explains how to *use* the emulator: how to create an
AVD, pass command-line flags, and forward ports. But if you need to understand
*how those features are implemented* — how a sensor value set over gRPC reaches
the guest's sensor HAL, how a `glDrawArrays` call in an app is encoded, shipped
across a pipe, and replayed against the host GPU, how Quickboot snapshots the
entire machine to disk and restores it in a second, or how `adb` finds an
emulator with no network device — there is no single source-referenced guide.

This book is that guide. Every architectural claim points at a specific file and,
where useful, a line, in the emulator source tree, so you can open the code and
read along.

### Who This Book Is For

- **Emulator and tools engineers** who need a map of an unfamiliar subsystem.
- **Platform and HAL developers** debugging guest behavior that only reproduces
  under emulation.
- **Graphics and virtualization engineers** working on gfxstream, ANGLE, or the
  QEMU device model.
- **Curious Android developers** who want to know what the green "play" button
  actually does.

### How This Book Is Organized

The chapters move bottom-to-top through the stack. Part I orients you and covers
the build. Part II is the QEMU foundation and CPU acceleration. Part III is the
`android-emu` core. Part IV is the graphics pipeline. Parts V–VII cover media,
connectivity, and the user interfaces. Part VIII follows the guest from system
image to boot, and Part IX covers testing and debugging.

### A Note on Source References

The emulator is a moving target. Line numbers drift; files are renamed; whole
subsystems are rewritten between releases. Treat the references here as a way to
find the right *place* in the tree, not as a guarantee that line 412 still says
what it said when this was written. When in doubt, `grep`.
