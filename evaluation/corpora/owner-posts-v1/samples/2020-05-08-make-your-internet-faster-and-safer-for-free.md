---
layout: post
title: "Make your internet faster and safer for free"
date: 2020-05-08T00:00:00.000-04:00
tags:
  - "Communications"
  - "News"
  - "Security"
  - "#Import 2025-06-30 17:59"
  - "#Import 2025-07-15 14:46"
authors:
  - "Kerry Hatcher"
feature_image: "https://images.unsplash.com/photo-1558981359-219d6364c9c8?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDExfHxtb3RvcmN5Y2xlfGVufDB8fHx8MTc0MTYxNTUwNHww&ixlib=rb-4.0.3&q=80&w=2000"
feature_image_caption: "<span style=\"white-space: pre-wrap;\">Photo by </span><a href=\"https://unsplash.com/@harleydavidson?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Harley-Davidson</span></a><span style=\"white-space: pre-wrap;\"> / </span><a href=\"https://unsplash.com/?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Unsplash</span></a>"
ghost_id: "6876a213df7b2049e70a063c"
ghost_url: "https://www.kerryhatcher.com/make-your-internet-faster-and-safer-for-free/"
---

Today we will be talking about the Domain Name System (DNS). Us lowly humans prefer to give things names while computers need numbers. DNS acts like the Internet’s phone book, translating name like `www.kerryhatcher.com` into an IP address like `104.16.23.84`. This process is rather fast, but due to a quark of modern web apps, has to happen several times on each website you visit.

---

***To be clear improving DNS lookup time won’t actually increase the throughput of your internet connection. A 300mbs connection would still be 300mbs. It will however increase the speed at which pages render on your screen and make downloads start faster (but not run faster).***

---

Take this visit to the [The Atlanta Journal-Constitution](https://www.ajc.com/?ref=kerryhatcher.com) home page. In order for the browser (Firefox in this case) to load the page, my computer had to send requests for 109 different things. Those are spread across a dozen or so hostnames each requiring a DNS lookup.

![](/assets/images/remote/hatchdata/images/2025/03/AJC_Load1.png)

Firefox has a really neat set of tools built in for looking at this sort of information. Just go to any website, right click, and select `inspect element`. From there just select the Network tab and refresh the page to watch all the requests pile up.

Lets take a look at an individual request. You will see that the browser took the most time just doing the DNS resolution. The actual download only took 124 ms vs the 283 ms to lookup the address in DNS.

![](/assets/images/remote/hatchdata/images/2025/03/AJC_Item_Load.png)

So you can see how if all these assets are waiting on DNS, the speed at which a page loads can be drastically impacted.

---

The issue that I’ve seen over the years is that DNS tends to be a bit of an afterthought among ISPs or is seen as a way to make money off your data. So they can be slower than you would want or they might be spying on you. The good news is that its relatively easy use a DNS server that your ISP doesn’t manage. Several great free options exist today for this including [OpenDNS](https://www.opendns.com/?ref=kerryhatcher.com), [Google DNS](https://developers.google.com/speed/public-dns?ref=kerryhatcher.com), [Quad9](https://www.quad9.net/?ref=kerryhatcher.com), and my favorite [CloudFlare DNS](https://1.1.1.1/?ref=kerryhatcher.com).

![](/assets/images/remote/hatchdata/images/2025/03/Screenshot-from-2020-05-08-18-20-23.png)

**Screen capture of DNS providers query speed according to** [**www.dnsperf.com/**](https://www.dnsperf.com/?ref=kerryhatcher.com#!dns-resolvers,North%20America)

---

![](/assets/images/remote/hatchdata/images/2025/03/cf-logo-h-rgb.png)

## My Favorite: CloudFlare’s 1.1.1.1

I have a few reasons why CloudFlare’s service is my favorite.

##### 1. Speed

There are plenty of sources [online](https://medium.com/%40nykolas.z/dns-resolvers-performance-compared-cloudflare-x-google-x-quad9-x-opendns-149e803734e5?ref=kerryhatcher.com) for the [numbers](https://www.dnsperf.com/?ref=kerryhatcher.com#!dns-resolvers,North%20America), but I can say that its usually in the top few of any comparison I’ve looked at.

##### 2. Privacy

Its fairly common practice to sell DNS logs data to determine web browsing habits. While on the surface this isn’t inherently bad, I’m just not a fan. Cloudflare has a well established reputation for [privacy](https://www.cnet.com/news/cloudflare-new-1111-dns-privacy-tool-would-speed-your-internet-too/?ref=kerryhatcher.com), and even recently [underwent an audit](https://blog.cloudflare.com/announcing-the-results-of-the-1-1-1-1-public-dns-resolver-privacy-examination/?ref=kerryhatcher.com) to show just how private it is.

##### 3. DNS Specs

This really gets me angry at some DNS providers. I vividly remember one time trying to troubleshoot an issue and this tripped me up. As far as I could tell my tools were indicating all was well but the application wasn’t working. It turns out my new ISP would respond with a functioning webserver IP address if a resolution failed. That server would return a webpage of search results. The official spec would have the server return an `nx domain`. so I wasted a very long time on that.

The trick was that the ISP was selling ads on the search page and was getting paid from the search engine. So it was just another way to milk me for more money.

##### 4. CloudFlare CDN

CloudFlare’s primary business is providing [CDN and WAF services](https://www.kerryhatcher.com/save-money-protect-your-site-with-a-cdn/). A significant number of websites you visit are probably already served by them (including this one). This means that if you us CloudFlare’s DNS you are more likely to get directed at the fastest website server available to you.

##### 5. Malware Protection

By default CloudFlare DNS is a by the book DNS provider. However, they do provide a another set of DNS servers that include a handy feature, they maintain a list of known domains that host Malware and won’t resolve them. So if you have kids (or even adults) that have issues getting garbage off random corners of the internet, this will help keep your computers clean and happy. Also since this runs at the DNS level, there is no impact to the performance of you computer.

---

## Cool, so how I get started?

If you are comfortable changing settings on your router or computer then the setup of Cloudflare or any of the others is straight forward.

There are two basic options; device config, or network config. If you setup your individual device (like your laptop) to use Cloudflare, then it won’t matter what network you are on (at home, or somewhere else) you will have the benefits of the service. With network config, you make changes to your router and all the devices on your network automatically start using the service of your choice.

CloudFlare has really good instructions at [https://1.1.1.1/dns/](https://1.1.1.1/dns/?ref=kerryhatcher.com). If you choose a different provider, they all have similar instructions.

**Note:** if you want to make use of Cloudflare’s malware protection, you will need to visit [https://1.1.1.1/family/](https://1.1.1.1/family/?ref=kerryhatcher.com) for instructions.

## What’s Firefox DoH?

Firefox has long had a focus on privacy. While setting up DNS isn’t the most complex process, it is still well above a vast number of people’s technical comfort level. The most effective privacy protections are those that happen by default. So newer versions of Firefox implement a protocol called DNS over HTTP (DoH). This means that Firefox will make DNS requests over encrypted HTTP (just like all other website traffic) to a default list of providers. Out of the box it actually uses Cloudflare, but users are able to select others from a list or disable the feature altogether.
