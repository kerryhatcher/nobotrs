---
layout: post
title: "Format and Mount EBS in Ubuntu"
date: 2011-05-03T22:00:00.000-04:00
tags:
  - "old"
  - "#Import 2025-06-30 17:59"
  - "#Import 2025-07-15 14:46"
authors:
  - "Kerry Hatcher"
feature_image: "https://images.unsplash.com/photo-1629654297299-c8506221ca97?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDF8fGxpbnV4fGVufDB8fHx8MTc0OTU3MzI0Nnww&ixlib=rb-4.1.0&q=80&w=2000"
feature_image_caption: "<span style=\"white-space: pre-wrap;\">Photo by </span><a href=\"https://unsplash.com/@6heinz3r?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Gabriel Heinzer</span></a><span style=\"white-space: pre-wrap;\"> / </span><a href=\"https://unsplash.com/?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Unsplash</span></a>"
ghost_id: "6876a213df7b2049e70a065e"
ghost_url: "https://www.kerryhatcher.com/format-and-mount-ebs-in-ubuntu/"
---

Once you have a server up and running with an extra disk, you'll need a few extra steps to get that disk ready for use.

\*Note: This is for the official Ubuntu 10.04 LTS AMI

1. SSH into your instance
2. mount
3. take note of the /dev/sdX that is mounted i.e. /dev/sda1 on / type ext3 (rw)
4. ls /dev
5. take note of the /dev/sdX that is not the one from step 3
6. fdisk /dev/sdX
7. At "Command" type n
8. at "Primary or Extended" type p
9. At Number of volumes type 1
10. Press "Return" two time to accept the defaults
11. Press W to write the changes and exit
12. type "mkfs.ext4 /dev/sdX" to format in Ext4
13. type "mkdir /media/ebs"
14. type "mount /dev/sdX /media/ebs" to mount the drive
