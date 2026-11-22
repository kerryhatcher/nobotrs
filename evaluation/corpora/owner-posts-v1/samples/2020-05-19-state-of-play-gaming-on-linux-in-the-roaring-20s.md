---
layout: post
title: "State of Play, Gaming on Linux in the roaring 20's"
dek: "Its the year of the Linux desktop... Again!! Let's talk gaming on Linux. "
date: 2020-05-19T00:00:00.000-04:00
tags:
  - "Gaming"
  - "Linux"
  - "News"
  - "#Import 2025-06-30 17:59"
  - "#Import 2025-07-15 14:46"
authors:
  - "Kerry Hatcher"
feature_image: "/assets/images/remote/hatchdata/images/2025/03/photo-1517784229726-7b866d820438.jpeg"
ghost_id: "6876a213df7b2049e70a0639"
ghost_url: "https://www.kerryhatcher.com/state-of-play-gaming-on-linux-in-the-roaring-20s/"
---

“This is the year Linux goes mainstream on the desktop”. I can’t tell you how many times I’ve heard that over the 20 years I’ve been using the [*GNU*](https://en.wikipedia.org/wiki/GNU?ref=kerryhatcher.com)*/Linux operating system*. The truth is open source desktops have always faced an uphill battle. A common complaint about Linux is the ability to play popular video game titles. However, things really have coalesced over the last few years to make options like Ubuntu a really compelling for everyday use by regular users.

On my personal laptop I’ve been dual-booting for a several years. Until late last year, I found myself spending most of my time in Windows and only using Ubuntu occasionally. Then my windows install crashed and I just kept putting off fixing it. I rediscovered just how much I enjoy using Linux as my daily driver. Eventually I fixed my windows partition, but it really didn’t get touched that much expect a few games that only ran on windows. Mostly [Sea of Thieves](https://www.seaofthieves.com/?ref=kerryhatcher.com) and [Player Unknown’s Battlegrounds (PUBG)](https://www.pubg.com/en-us/?ref=kerryhatcher.com)

## Drivers and Porting

The two main things holding back serious gaming on Linux has traditionally been the dual struggle of video card drivers and [porting the games to a new OS](https://anteru.net/blog/2014/porting-from-windows-to-linux-part-1/?ref=kerryhatcher.com). There has been some very clear progress over the last 3 years or so on both fronts. Progress driven by big players in the industry.

### Video Card Drivers

Video games are inherently taxing on computers. Most games require the use of dedicated video cards to render the graphics of the games. Traditionally there has been a lack of cooperation between the hardware vendors (AMD and NVIDIA) and the opensource community. This is mostly due the the need for the hardware vendors to maintain control over their “secret sauce” intellectual property. Since there isn’t a central company behind Linux, there hasn’t been someone who could engage them like Microsoft or Apple can.

That changed recently with [Ubuntu starting to ship the NVIDIA drivers](https://ubuntu.com/blog/whats-new-in-ubuntu-desktop-20-04-lts?ref=kerryhatcher.com) with the OS (much like Microsoft). [They also made configuring and making changes significantly easier](https://www.forbes.com/sites/jasonevangelho/2020/03/03/ubuntu-2004-makes-picking-the-right-graphics-driver-less-confusing/?ref=kerryhatcher.com#4463c3af5a57). [NVIDIA](https://www.phoronix.com/scan.php?page=news_item&px=NVIDIA-Contributions-2010s-Kern&ref=kerryhatcher.com) and [AMD](https://www.phoronix.com/scan.php?page=article&item=linux-54-radeon&num=1&ref=kerryhatcher.com) have also themselves made Linux support a higher priority driven mostly by the [high performance computer industry](https://www.nics.tennessee.edu/computing-resources/what-is-hpc?ref=kerryhatcher.com) where [Linux holds a large market share](https://www.top500.org/statistics/details/osfam/1?ref=kerryhatcher.com).

Another major development has been the adoption of the [Vulkan graphics API](https://www.khronos.org/vulkan/?ref=kerryhatcher.com). Without going into the super nerdy realm, suffice it to say that having a unified API across Linux and Windows makes graphic intensive applications easier to develop for both [OSes](https://en.wiktionary.org/wiki/OSes?ref=kerryhatcher.com). Also its worth noting that developers are starting to pick up Vulkan due [to its performance](https://www.kitguru.net/gaming/dominic-moass/vulkan-vs-dx12-red-dead-redemption-2-pc-performance-analysis/?ref=kerryhatcher.com) and getting up [better Linux compatibility](https://www.cedega.com/2017/10/14/vulkan-graphics-api/?ref=kerryhatcher.com) along the way.

### Porting to Linux

Writing software to run on multiple operating systems is tedious and resource intensive. This is generally why game publishers shy away from supporting Linux since the OS holds a rather small percentage of the desktop market.

The good news is that there exists a project that allows a program written for windows to run on Linux without any changes by translating the windows system calls to Linux ones. The [WINE project](https://www.winehq.org/?ref=kerryhatcher.com) has been around for many years and is supported by a growing list of dedicated developers. However, WINE doesn’t support every possible command a given application may try. So not all applications run perfectly and may require some hoop jumping to make work. This is non-trivial for the average user.

Even better news is that Valve (the company behind Steam) starting supporting the [WINE project directly in 2016](https://steamcommunity.com/games/221410/announcements/detail/1696055855739350561?ref=kerryhatcher.com). This was in support of their Steam Machine project which was based on Linux. It was also in response to the backlash from the release of windows 8. They call their custom version of WINE [“Proton”](https://www.protondb.com/?ref=kerryhatcher.com).

![](https://old.kerryhatcher.com/images/state-of-play-gaming-on-linux/image-11.png)

Now you can download and install steam directly on Ubuntu and enjoy [a growing list of games](https://www.protondb.com/?ref=kerryhatcher.com) certified to run on Linux. Many of these games were not ported by the developers, but rather the features needed to run them were added to the upstream WINE project. Here is the list of my favorite games I play on Linux (Ubuntu 20.04) via Steam:

![](https://old.kerryhatcher.com/images/state-of-play-gaming-on-linux/image-15.png)

A common issue that prevents games from running under WINE (or Proton as valve calls it) is anti-cheat systems. This is why games like [PUBG](https://www.pubg.com/en-us/?ref=kerryhatcher.com) and [Valorant](https://beta.playvalorant.com/en-us/?ref=kerryhatcher.com) don’t run on Linux. The other primary issue is games published exclusively under the Microsoft store (like [Sea of Thieves](https://www.seaofthieves.com/?ref=kerryhatcher.com)). There isn’t much anyone other than Microsoft can do about that, and I don’t see them giving that up anytime soon.

Vist [https://store.steampowered.com/linux](https://store.steampowered.com/linux?ref=kerryhatcher.com) to see the current list of games you can play on Linux via Steam.

*Top Linux games on steam by sales or playtime*

---

## What about games not supported by Steam Play?

Don’t despair, there are still options.

### Steam

![](https://old.kerryhatcher.com/images/state-of-play-gaming-on-linux/image-5.png)

Its worth noting that even games not officially supported by Steam Play / Proton can still run just fine. One of my all time favorite games [Age of Empires II](https://en.wikipedia.org/wiki/Age_of_Empires_II?ref=kerryhatcher.com) runs just fine on Linux but its not on Steam’s supported list. Considering it was originally developed by Microsoft in 1999, It runs great on Linux via Steam Play/Proton and is still very entertaining. C[heck out this really good article on how to enable this ability in Steam](https://itsfoss.com/steam-play/?ref=kerryhatcher.com)

### Wine / CodeWeavers

![](https://old.kerryhatcher.com/images/state-of-play-gaming-on-linux/image-9.png)

For any games that are not distributed via Steam or Steam games that don’t won’t cooperate, you still have options. The Wine application has a crazy number of options that you can try to get things working. There are tons of other blogs, forums, and other online sources created by fellow gamers trying to get their favorite games working.

Its going to take plenty of work to figure it out, but the results can sometimes be games that perform even better than on Windows. This was case for Blizzard’s World of Warcraft. It took me a very long time to figure out, but once I did it ran so much better than on Windows.

If your not really down for digging though all those options you may still consider using CodeWeaver’s supported version of Wine. It will cost you about $60 but they have a really nice interface that helps get Wine working correctly. Plus they have professional support if you need it.

---

### How you can help

![](https://old.kerryhatcher.com/images/state-of-play-gaming-on-linux/image-12.png)

Proton (Steam), Wine, and CodeWeavers all rely on user feedback for bug reports and play ability ratings. If your game works fine, or if it has issues, please report that back.

Visit [protondb.com](https://www.protondb.com/?ref=kerryhatcher.com) to report any issues with Steam games

To file reports or check an apps status on WINE visit: [appdb.winehq.org](https://appdb.winehq.org/?ref=kerryhatcher.com)

Finally; check this page out for CodeWeavers: [www.codeweavers.com/compatibility](https://www.codeweavers.com/compatibility?ref=kerryhatcher.com)

---

## Native Games

While the vast majority of games are only ever released for Windows and a few for MacOS, there are still some really good games out there that are officially supported on Linux.

Here are a few of my favorites:

### FreeCiv (Free)

[FreeCiv](http://www.freeciv.org/?ref=kerryhatcher.com) is similar to the [Civilization series](https://civilization.com/?ref=kerryhatcher.com). While it doesn’t have the super shiny graphics that the new commercial Civilization games, the game-play is still very entertaining. Its maintained by a small dedicated group of volunteers and is very stable. I’ve spent many hours over the years playing and it never disappoints.

You can install FreeCiv on Ubuntu 20.04 with a single command:

`sudo apt install freeciv`

---

### Factorio (Paid)

![](https://old.kerryhatcher.com/images/state-of-play-gaming-on-linux/image-13.png)

Another very addictive game. The basic premise is that you are a stranded engineer on an alien planet. Starting off with little more than your hands, you must develop all the industry to build a rocket and get off the planet. This game really gets fun with you play with your friends. If you happen to do process or automation engineering professionally, this will really scratch an itch.

You can get Factorio directly from their website or via Steam. Even though its available via steam, its still a native Linux game so its going to work really well. I’d recommend purchasing via Steam, it will make installing and updating much easier.
