---
layout: post
title: "It's time to switch to a new email provider."
date: 2020-05-11T00:00:00.000-04:00
tags:
  - "News"
  - "Security"
  - "Communications"
  - "#Import 2025-06-30 17:59"
  - "#Import 2025-07-15 14:46"
authors:
  - "Kerry Hatcher"
feature_image: "/assets/images/remote/hatchdata/images/2025/03/protonmail-corporate-door.jpg"
ghost_id: "6876a213df7b2049e70a063a"
ghost_url: "https://www.kerryhatcher.com/its-time-to-switch-to-a-new-email-provider/"
---

Email has become the gateway into the vast majority of the online applications we use every day. From Facebook to Amazon, your email is your identity. The very reason there are so many “free” email providers out there is because your data is extremely valuable. I’ve heard the saying a few times “if you are not paying for the service, you are the product”.

Another big concern beyond privacy is security. Ever forgot your password for one of the online services you use? Perhaps your online bank? When you click that reset password link, usually you get an email with a link that lets you reset your password. This means that anyone who has access to your email has access to all those other services.

Most people don’t understand just how insecure email messages are at a basic level. The best physical analogy for it would be a postcard. When you send an email, the message is sent across the internet via several different networks. The sender, the recipient, and the entire email contents is in plain text. Anyone who has access to any of the networks can read all of that and no one would know.

There are some technologies out there that allow someone to encrypt emails but they tend to be cumbersome to use and are not for someone who isn’t a techie. [PGP](https://en.wikipedia.org/wiki/Pretty_Good_Privacy?ref=kerryhatcher.com) (and [GPG](https://gnupg.org/?ref=kerryhatcher.com)) have been around for a long time and are well proven, but I can tell you it’s not easy to use correctly. Generally, if some security process is hard most folks won’t do it correctly or at all. The best security is that which is seamless and easy for users.

---

## I recommend you consider [ProtonMail](https://protonmail.com/?ref=kerryhatcher.com)

![](/assets/images/remote/hatchdata/images/2025/03/homepage.jpg)

ProtonMail was specifically designed with security and privacy in mind. It uses PGP to encrypt emails to anyone else who has shared their keys (such as another ProtonMail user) without any software to setup. They create and manage the keys for you so you don’t have to worry about setting that up wrong.

[Read about ProtonMail threat model here](https://protonmail.com/blog/protonmail-threat-model/?ref=kerryhatcher.com)

---

![](/assets/images/remote/hatchdata/images/2025/03/secured-by-protonmail-purple.png)

### Security

Not having control of your keys is in of itself a security risk, however, having a trusted entity handle it for you is way better than nothing at all. Also, it’s important to note that unless ProtonMail knows the keys for the recipient of your email, it still sends plain old emails. ProtonMail does a good job and attempting to send email over [TLS](https://en.wikipedia.org/wiki/Transport_Layer_Security?ref=kerryhatcher.com) ( a different kind of encryption) to other email providers so that network operators in the middle can’t read them. But even an email sent over TLS from one server to the next is still not encrypted while it sits on that server. [Read more here.](https://protonmail.com/security-details?ref=kerryhatcher.com)

Also, [ProtonMail supports two-factor authentication](https://protonmail.com/support/knowledge-base/two-factor-authentication/?ref=kerryhatcher.com). This will help prevent any unauthorized access to your account.*Example screenshots from ProtonMail*

---

![](/assets/images/remote/hatchdata/images/2025/03/column-message.jpg)

**Example screenshots from ProtonMail**

---

![](/assets/images/remote/hatchdata/images/2025/03/protonmail-shot-girl.jpg)

### Privacy

This is where ProtonMail shines. Since they are a professional email hosting company they are not using the data they collect to fund the company. They rely on paying customers to cover the cost of the business. Additionally, being based in Switzerland, they are covered by some of the most stringent privacy laws in the world. You can see their transparency report here listing all the warrants they have received.

---

![](/assets/images/remote/hatchdata/images/2025/03/protonmail-shot-decrypt.jpg)

### Encrypted Email on the Go

One of the biggest drawbacks to using PGP/GPG is the inability to decrypt/encrypt emails on mobile devices. ProtonMail has native mobile apps that handle all that transparently for you. So you can still have your email on the go, and not lose any of your privacy or security.

![](/assets/images/remote/hatchdata/images/2025/03/inbox.jpg)

---

### Price

One of the really neat things about ProtonMail is that you can use it at no cost. Yes, I know, I just bashed on other services about that. The trick is that the free version has a fairly limited mailbox size, especially compared to something like Gmail. Many users will be fine using the free version, you will just need to keep those automated emails to a minimum and delete unneeded emails. The premium subscriptions start at $5 a month and go up to $30 a month.

![](/assets/images/remote/hatchdata/images/2025/03/image-5.png)

---

### Bonus: VPN service

![](/assets/images/remote/hatchdata/images/2025/03/protonvpn-wallpaper-7.jpg)

If you know “they” are after you then you can step up your game with Proton’s VPN service. With this, your internet traffic is tunneled to their servers before going out to the internet. This helps keep anyone from spying on your browsing habits. Nothing more satisfying to the security nerd than sending GPG encrypted email over TLS via an encrypted VPN. Take that NSA!

Just like their email service, VPN starts free and the free version is good enough for most users.

---

#### Warning, its about to get real nerdy.

![](/assets/images/remote/hatchdata/images/2025/03/image-1-1.png)

Access via the “Dark Web”

ProtonMail has been so good at keeping people’s secrets it has prompted some authoritarian [regimes to block it](https://www.reuters.com/article/us-russia-protonmail/russia-blocks-encrypted-email-service-protonmail-idUSKBN1ZS1K8?ref=kerryhatcher.com). [Many years ago researchers](https://www.torproject.org/about/history/?ref=kerryhatcher.com) at the U.S. Naval Research Lab (NRL) and Massachusetts Institute of Technology (MIT) began working on a technology that would allow for true anonymity between users and servers called [Onion Routing](https://en.wikipedia.org/wiki/Onion_routing?ref=kerryhatcher.com). The primary goal was to get around government censorship to access the open internet (example: [great firewall of China](https://en.wikipedia.org/wiki/Great_Firewall?ref=kerryhatcher.com)).

To help facilitate the use of ProtonMail by journalists and dissidents in repressive countries (or for those of us in the tinfoil hat crowd) [ProtonMail operates a dedicated](https://protonmail.com/tor?ref=kerryhatcher.com) [“onion” page](https://protonirockerxow.onion/?ref=kerryhatcher.com) accessible via the [Tor Browser](https://www.torproject.org/download/?ref=kerryhatcher.com) (a custom version of FireFox).

Tor is also a great way to keep your browsing history safe, however it’s also a very technically difficult system to get right without risking mistakes. Tor browser was created to make that seamless and easy for non-technical users. It’s basically a modified version of FireFox that ensures all traffic is protected.

Just be careful out there, [the dark web is the wild west](https://en.wikipedia.org/wiki/Dark_web?ref=kerryhatcher.com). Use it only for good.

---

Go ahead and sign up for a free account at ProtonMail and kick the tires. If you like it then consider switching to it full time. Then consider supporting them buy purchasing a subscription. There is nothing to risk by giving it a shot and lots to gain.

Personally, I use the visionary plan. I just value their service that much. Feel free to send me an encrypted email once you get set up. It’s my firstname.lastname @ the same domain yours will be when you get your new email address. For the real nerds out there my key fingerprint is a8b69ee8330f57205a6bf2bf119b8df063df9d43
