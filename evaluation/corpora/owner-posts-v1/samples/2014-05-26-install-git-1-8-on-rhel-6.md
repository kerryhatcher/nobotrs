---
layout: post
title: "Install Git 1.8 on RHEL 6"
date: 2014-05-26T10:29:00.000-04:00
tags:
  - "old"
  - "technology"
  - "Linux"
  - "#Import 2025-06-30 17:59"
  - "#Import 2025-07-15 14:46"
authors:
  - "Kerry Hatcher"
feature_image: "https://images.unsplash.com/photo-1598439210625-5067c578f3f6?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDF8fHBlbmd1aW58ZW58MHx8fHwxNzQ5NTc1NDkzfDA&ixlib=rb-4.1.0&q=80&w=2000"
feature_image_caption: "<span style=\"white-space: pre-wrap;\">Photo by </span><a href=\"https://unsplash.com/@corneliusventures?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Cornelius Ventures</span></a><span style=\"white-space: pre-wrap;\"> / </span><a href=\"https://unsplash.com/?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Unsplash</span></a>"
ghost_id: "6876a213df7b2049e70a0665"
ghost_url: "https://www.kerryhatcher.com/install-git-1-8-on-rhel-6/"
---

While PyCharm does work with the native version of Git that ships with RHEL 6.5, it does complain a lot. I also feared that something would go wrong eventually so I started looking around on updating.

There wasn't a newer version of Git in fast track so I had to go with something else. Luckily I found the [IUS Community Project.](https://iuscommunity.org/pages/About.html?ref=kerryhatcher.com)

> The IUS Community Project is aimed at providing up to date and regularly maintained RPM packages for the latest upstream versions of PHP, Python, MySQL and other common software specifically for Redhat Enterprise Linux. IUS can be thought of as a better way to upgrade RHEL, when you need to.

The project is sponsored by Rackspace and is a spin off of their own internal project. A huge plus is that it is [SafeRepo Aware](https://iuscommunity.org/pages/About.html?ref=kerryhatcher.com). Meaning that when I installed the repo I couldn't just do a yum update and get the latest version of git (along with any other software and totally wreak my system). To install git 1.8 I had to yum install git18

Now when I yum search git, I see (along with others):

> git.x86\_64 : Fast Version Control System
> git18.x86\_64 : Fast Version Control System

So I can choose which version I want without upgrading all the great stock RHEL packages on my system.

Well enough of my talking, to the script!!

Latest version is at Github:
[https://github.com/kerryhatcher/HatchScripts/blob/master/Git18.sh](https://www.blogger.com/?ref=kerryhatcher.com)

As Root:

> wget http://dl.iuscommunity.org/pub/ius/stable/Redhat/6/x86\_64/epel-release-6-5.noarch.rpm
>
> yum install epel-release-6-5.noarch.rpm
>
> wget http://dl.iuscommunity.org/pub/ius/stable/Redhat/6/x86\_64/ius-release-1.0-11.ius.el6.noarch.rpm
>
> yum install ius-release-1.0-11.ius.el6.noarch.rpm
>
> yum install git18
