---
layout: post
title: "Taking Control of Your Email - Part 2: Using Your Own Domain for Email"
dek: "Still using a @gmail.com for your business or personal brand? Learn how to set up email on your own domain and gain privacy, control, and professionalism—without breaking the bank."
date: 2025-06-05T06:20:17.000-04:00
tags:
  - "#Import 2025-06-30 17:59"
  - "#Import 2025-07-15 14:46"
authors:
  - "Kerry Hatcher"
feature_image: "https://images.unsplash.com/photo-1600267165477-6d4cc741b379?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDIzfHxlbWFpbHxlbnwwfHx8fDE3NDg5NzYwODd8MA&ixlib=rb-4.1.0&q=80&w=2000"
feature_image_caption: "<span style=\"white-space: pre-wrap;\">Photo by </span><a href=\"https://unsplash.com/@sigmund?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Sigmund</span></a><span style=\"white-space: pre-wrap;\"> / </span><a href=\"https://unsplash.com/?utm_source=ghost&amp;utm_medium=referral&amp;utm_campaign=api-credit\"><span style=\"white-space: pre-wrap;\">Unsplash</span></a>"
ghost_id: "6876a213df7b2049e70a065b"
ghost_url: "https://www.kerryhatcher.com/taking-control-of-your-email-part-2-using-your-own-domain-for-email/"
---

One of the best decisions you can make to level up your email setup is to use your **own custom domain**. There are numerous benefits to doing this, and while it requires a bit of technical setup, it’s well worth the effort. Let’s walk through *why* and *how* to use your own domain for email, using Fastmail and Cloudflare DNS as concrete examples.

[Taking Control of Your Email - Part 1: Choosing a Private Email Provider

Tired of Gmail reading your emails? Learn how to choose a private, secure provider that puts you in control. Privacy isn’t just for whistleblowers—ditch Big Tech and take back your inbox.

![](/assets/images/remote/hatchdata/images/icon/cc763bb925375f8868f6cfd4bfa334ca-1-10.jpeg)Kerry HatcherKerry Hatcher

![](/assets/images/remote/hatchdata/images/thumbnail/photo-1596526131083-e8c633c948d2)](https://www.kerryhatcher.com/taking-control-of-your-email-part-1-choosing-a-private-email-provider/)

Checkout Part 1 if you haven't already

### Why Use a Custom Domain for Email?

* **Professionalism and Personal Branding:** An email like `alice@yourdomain.com` immediately looks more professional (and is easier to remember) than `alice1977@gmail.com`. Whether for personal use or business, it shows you’ve put thought into your online identity. If you have a business or a personal brand (even if it’s just your last name), a custom domain email reinforces that branding every time you send a message.
* **Portability and Control:** Arguably the biggest advantage is that **you own your address**, not Big Tech. If you ever decide to switch email providers, you can take your email address with you. For example, you could start by using your domain with Fastmail, and later if another service catches your eye, you can move – without having to inform all your contacts of a new address. As Fastmail’s help docs put it, owning your domain means you can keep your email address the same no matter what provider you use. It decouples your identity from the service. This also insulates you from a provider shutting down or changing terms; *you* call the shots for your domain.
* **Flexibility with Addresses:** When you control a domain, you can set up multiple addresses and aliases freely. You might have `alice@yourdomain.com` for personal mail, `info@yourdomain.com` for newsletter signups, and perhaps `billing@yourdomain.com` for financial accounts – all ultimately delivered to the same inbox (or separate ones, you decide!). Many email hosts, Fastmail included, support “catch-all” addresses on custom domains – meaning any address at your domain will reach you unless you specifically block it. This can be great for using unique addresses per service (for privacy and tracking which companies might leak your email). While some providers allow plus-addressing on their domain (e.g. `alice+newsletter@gmail.com`), a custom domain gives you far more freedom in address naming.
* **Consistency for Groups:** If you set up email for a family or team, a domain gives consistency. Your family might all use `@smithfamily.com` addresses, which is easier for correspondents to recognize. And if an individual leaves the team or family setup, you can reassign or forward their address as needed.

Now that the *why* is clear, let’s dive into the *how*. We’ll cover buying a domain, setting up DNS records (using Cloudflare), and verifying everything works.

---

![woman in black top using Surface laptop](https://images.unsplash.com/photo-1573164713988-8665fc963095?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDEwOXx8bmV0d29ya3xlbnwwfHx8fDE3NDg5NzY5MTR8MA&ixlib=rb-4.1.0&q=80&w=2000)

Photo by [Christina @ wocintechchat.com](https://unsplash.com/%40wocintechchat?ref=kerryhatcher.com) / [Unsplash](https://unsplash.com/?utm_source=ghost&utm_medium=referral&utm_campaign=api-credit)

### 1. Buying a Domain Name

If you don’t already have a domain, you’ll need to purchase one from a **domain registrar**. Popular registrars include Namecheap, Google Domains (now part of Squarespace), GoDaddy, Hover, Cloudflare Registrar, and many more. When choosing a registrar, consider a few factors:

* **Pricing and Renewal Rates:** Domains are usually cheap in the first year (often $10–15 for a .com for instance), but some registrars hike the price on renewal. Read the fine print. Also check if they charge extra for things like WHOIS privacy (which masks your personal info on the public registry – many registrars now include this free by default, which is good for privacy).
* **DNS Management Features:** Since you plan to use custom DNS records for email, make sure the registrar allows you to manage DNS records easily. Most do, but some budget providers or web-hosting bundles can be limited. In our case, we’ll actually use Cloudflare to manage DNS, so the registrar’s DNS interface isn’t critical – but you still need a registrar that lets you *change nameservers* (to point to Cloudflare). Virtually all do, but avoid any service that tries to lock you in.
* **Support and Reputation:** It can be worth a few extra dollars to use a registrar known for good support and a clean interface. Namecheap and Cloudflare are both known for simplicity and fair policies. GoDaddy, while big, is often critiqued for upsells in the UI. Since domain management is something you might only rarely touch, a straightforward dashboard is nice to have.

Once you’ve picked a registrar, search for your desired domain name to see if it’s available. For example, if you want `yourlastname.com` or something quirky related to you. If your first choice is taken, consider different TLDs (maybe `.net`, `.io`, `.me`, etc., though for personal email `.com` or `.me` are common and widely recognized). After purchasing, you’ll have an account at the registrar where you can manage the domain.

One important note: **registrar vs DNS host.** You can buy a domain from one company and host the DNS somewhere else. In fact, we’ll do exactly that: buy the domain (or use an existing one) and then use Cloudflare’s free DNS hosting for it.

---

![a close up of a computer keyboard in the dark](https://images.unsplash.com/photo-1623018034840-2434c8403b94?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDEyMHx8aW50ZXJuZXR8ZW58MHx8fHwxNzQ4OTc3MTI0fDA&ixlib=rb-4.1.0&q=80&w=2000)

Photo by [David Pupăză](https://unsplash.com/%40davfts?ref=kerryhatcher.com) / [Unsplash](https://unsplash.com/?utm_source=ghost&utm_medium=referral&utm_campaign=api-credit)

### 2. Pointing Your Domain to Cloudflare DNS

Cloudflare is widely recommended for DNS hosting due to its speed, reliability, and security measures. As mentioned in an earlier post on improving DNS speed, [Cloudflare’s DNS service is both fast and privacy-conscious](https://www.kerryhatcher.com/make-your-internet-faster-and-safer-for-free/). Here, we’ll use Cloudflare to manage our domain’s DNS records (while still keeping the domain registered wherever we bought it).

**Steps to use Cloudflare DNS:**

1. **Create a Cloudflare account:** If you don’t have one, sign up at Cloudflare (it’s free for our purposes). Once logged in, you can add a new site/domain to Cloudflare.
2. **Add your domain in Cloudflare:** In the Cloudflare dashboard, you’ll typically find an **“Add Site”** button. Enter your domain (e.g. `yourdomain.com`). Cloudflare will then scan any existing DNS records it can find. Since our goal is email, you might not have many records yet (except maybe defaults). It’s okay; Cloudflare will let you review and add records later.
3. **Update Nameservers at Registrar:** When you add a domain, Cloudflare assigns you two nameserver addresses (something like `gabe.ns.cloudflare.com` and `lisa.ns.cloudflare.com`, for example). You need to go back to your domain registrar’s control panel and find where to set *nameservers* for your domain. Replace whatever is there (often default nameservers from the registrar) with the Cloudflare ones. This step delegates DNS authority to Cloudflare. (It may take a couple hours to propagate, but usually is pretty fast.)
4. **Confirm on Cloudflare:** Cloudflare will detect when your domain’s nameserver change has gone through. Once it’s confirmed, you can manage all DNS records via Cloudflare’s dashboard.

At this point, Cloudflare is effectively your DNS manager. The domain still *belongs* to you via the registrar, but all DNS queries (like “where should email for @yourdomain.com go?”) will be answered by Cloudflare according to the records you set.

---

![person using silver laptop computer on desk](https://images.unsplash.com/photo-1516321165247-4aa89a48be28?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDl8fGludGVybmV0fGVufDB8fHx8MTc0ODk3NzA3MHww&ixlib=rb-4.1.0&q=80&w=2000)

Photo by [John](https://unsplash.com/%40johnishappysometimes?ref=kerryhatcher.com) / [Unsplash](https://unsplash.com/?utm_source=ghost&utm_medium=referral&utm_campaign=api-credit)

### 3. Adding DNS Records for Email (MX, SPF, DKIM, DMARC, etc.)

Now comes the key configuration to get email working with your provider (Fastmail in this example). There are a few types of DNS records we need to add:

* **MX (Mail eXchanger) Records:** These tell the world which mail server handles email for your domain. Essentially, “if you have mail for *@yourdomain.com*, send it to these server(s).” Usually, you’ll have two MX records for redundancy. Fastmail’s docs say the MX for your domain should point to `in1-smtp.messagingengine.com` (priority 10) and `in2-smtp.messagingengine.com` (priority 20)[fastmail.help](https://www.fastmail.help/hc/en-us/articles/360060591153-Manual-DNS-configuration?ref=kerryhatcher.com#:~:text=Type%20Host%20Value%20Priority%20MX,smtp.messagingengine.com%60%20%6020). The lower number priority is tried first, the second is backup. For other providers, the addresses will be different (e.g., ProtonMail might be `mail.protonmail.ch` etc., Mailfence uses `mx.mailfence.com`). We’ll illustrate with Fastmail’s records.
* **SPF (Sender Policy Framework) – TXT Record:** SPF is a simple allowlist of servers permitted to send mail *on behalf of your domain*. Publishing an SPF TXT record helps receiving mail servers know, when they get an email claiming to be from *@yourdomain.com*, whether the sending server was legit. Fastmail provides an SPF string to use. For instance, their recommended SPF record is:
  `v=spf1 include:spf.messagingengine.com -all`
  This means “For my domain, the allowed senders are those listed in Fastmail’s SPF include (their servers), and no others (-all)”. We’ll add this as a TXT record on Cloudflare.
* **DKIM (DomainKeys Identified Mail) – typically CNAME or TXT:** DKIM works by having your mail server digitally sign each outgoing email. The recipient can verify the signature by looking up a public key in your domain’s DNS. So, you need to add that public key record. Fastmail (and many others) make this easy by giving you DNS records to plug in. Fastmail uses three DKIM selector keys by default (fm1, fm2, fm3). They provide them as CNAME records – for example:
  `fm1._domainkey.yourdomain.com -> fm1.yourdomain.com.dkim.fmhosted.com` (That target is a Fastmail-hosted DNS name that resolves to the actual key.) Some providers might give you a long `TXT` record instead containing the public key string. Either way, adding the DKIM records is crucial to ensure your emails get authenticated as genuinely from you and not tampered with. Don’t worry – you usually just copy-paste what your email host provides.
* **DMARC (Domain-based Message Authentication, Reporting & Conformance) – TXT Record:** DMARC builds on SPF and DKIM. It’s a policy that tells receivers what to do if an email fails SPF/DKIM checks. It can also request reports so you can see if anyone’s spoofing your domain. A basic DMARC record might look like:
  `v=DMARC1; p=none; rua=mailto:postmaster@yourdomain.com`
  This says “I’m publishing DMARC. For now, do nothing (p=none) if my mail fails checks, but send reports to postmaster@mydomain.” Once you’re confident SPF/DKIM are set up right, you might change `p=none` to `p=quarantine` (send failures to spam) or `p=reject` (reject failures outright) to enforce protection against spoofed emails. Fastmail’s setup suggests at least a basic DMARC record[fastmail.help](https://www.fastmail.help/hc/en-us/articles/360060591153-Manual-DNS-configuration?ref=kerryhatcher.com#:~:text=DMARC). We’ll add a TXT record at `_dmarc.yourdomain.com` with our policy. If using Fastmail, you could use their suggested default or customize.
* **Additional (Optional) Records:**
  + **Autodiscover/Autoconfig SRV or CNAME:** Some email providers suggest adding records to help email clients auto-configure. Fastmail, for example, lists SRV records for autodiscovery of IMAP/POP/SMTP settings[fastmail.help](https://www.fastmail.help/hc/en-us/articles/360060591153-Manual-DNS-configuration?ref=kerryhatcher.com#:~:text=SRV%20%60_pop3s._tcp.,mydomain.com%7D%60%20%600%60%20%601%60%20%60443%60%20%60autodiscover.fastmail.com). These aren’t strictly required but can improve user experience when setting up clients – e.g., Outlook might find the right servers automatically if these exist. You might see something like `_imap._tcp.yourdomain.com SRV 0 1 993 imap.fastmail.com` and similar for SMTP[fastmail.help](https://www.fastmail.help/hc/en-us/articles/360060591153-Manual-DNS-configuration?ref=kerryhatcher.com#:~:text=Type%20Host%20Priority%20Weight%20Port,mydomain.com%7D%60%20%600%60%20%601%60%20%60443%60%20%60autodiscover.fastmail.com). If you’re comfortable adding them, it doesn’t hurt.
  + **Custom DKIM selectors:** If you use multiple email services for one domain (rare, but say you have some emails sent by a newsletter service), you’d have additional DKIM records from those services. Keep track of those if applicable.
  + **Subdomain MX:** Generally not needed unless you want something like a subdomain (mail.yourdomain.com) to handle mail separately. Most will use the root domain for email.

***Cloudflare Example:***

Let’s add these records in Cloudflare. In the Cloudflare DNS dashboard for your domain, you’d click **“Add Record”** for each needed entry:

*Cloudflare DNS management interface for adding records.*

* *MX Record:* Choose **MX** from the type dropdown. For **Name**, you typically leave it blank or `@` to represent your root domain. For **Mail server**, enter the address given (e.g. `in1-smtp.messagingengine.com`), and set Priority to 10. Add a second MX with priority 20 pointing to the secondary server (`in2-smtp.messagingengine.com`). Cloudflare will display them as a list once added. (Ensure **Proxy status** is **DNS Only** – Cloudflare can’t proxy SMTP, so it should be the default gray cloud.)
* *SPF Record:* This is a TXT record. Choose **TXT** type. Name = `@` (root domain). Content = the SPF string, e.g. `v=spf1 include:spf.messagingengine.com -all`. TTL can be left at auto or 1 hour. Save.
* *DKIM Records:* For Fastmail’s three DKIM CNAMES, add each one. Type **CNAME**. Name = `fm1._domainkey` (Cloudflare will auto-append `.yourdomain.com`). Target = `fm1.yourdomain.com.dkim.fmhosted.com`[fastmail.help](https://www.fastmail.help/hc/en-us/articles/360060591153-Manual-DNS-configuration?ref=kerryhatcher.com#:~:text=Type%20Host%20Value%20CNAME%20%60fm1._domainkey.,mydomain.com%7D.dkim.fmhosted.com). Repeat for `fm2._domainkey` and `fm3._domainkey` with their respective targets[fastmail.help](https://www.fastmail.help/hc/en-us/articles/360060591153-Manual-DNS-configuration?ref=kerryhatcher.com#:~:text=Type%20Host%20Value%20CNAME%20%60fm1._domainkey.,mydomain.com%7D.dkim.fmhosted.com). (For other providers, if they gave a TXT, you’d put Name like `default._domainkey` and paste the provided key in Content.)
* *DMARC Record:* Type **TXT**. Name = `_dmarc` (Cloudflare will append yourdomain.com, making it `_dmarc.yourdomain.com`). Content = your DMARC policy string, e.g. `v=DMARC1; p=none; rua=mailto:postmaster@yourdomain.com;`. (You can omit the report email if you don’t want reports, or use an external service to collect them.) Setting `p=none` initially is wise – it monitors without affecting delivery, so you can check that SPF/DKIM are passing before enforcing stricter action.
* *Autodiscover SRV (optional):* If adding, it goes like this: choose **SRV** record. Service name in Cloudflare will be like `_autodiscover._tcp` (Cloudflare splits fields for SRV: you might enter “\_autodiscover” as Service and “\_tcp” as Protocol, then priority, weight, port, target in respective fields). For Fastmail, the SRV for autodiscover is `_autodiscover._tcp.yourdomain.com -> priority 0, weight 1, port 443, target autodiscover.fastmail.com`[fastmail.help](https://www.fastmail.help/hc/en-us/articles/360060591153-Manual-DNS-configuration?ref=kerryhatcher.com#:~:text=SRV%20%60_pop3s._tcp.,mydomain.com%7D%60%20%600%60%20%601%60%20%60443%60%20%60autodiscover.fastmail.com). They also list ones for `_submission._tcp` and others for SMTP/IMAP with either target or “.” if not used[fastmail.help](https://www.fastmail.help/hc/en-us/articles/360060591153-Manual-DNS-configuration?ref=kerryhatcher.com#:~:text=Type%20Host%20Priority%20Weight%20Port,mydomain.com%7D%60%20%600%60%20%601%60%20%60443%60%20%60autodiscover.fastmail.com). This is advanced; casual users can skip it, but it’s there for completeness.

After entering these, Cloudflare will have a list of DNS records for your domain. **Double-check for typos** – a missing dot or an extra space can break things. Common pitfalls include: forgetting to remove the default MX (if any) from the registrar (Cloudflare might have imported an MX like mail.yourdomain.com which you should delete if you’re using Fastmail’s MX), or accidentally having two SPF records (you should only have one SPF TXT – if multiple, combine them).

Give it a few minutes to propagate. DNS TTLs we set (like 1 hour) mean within an hour, the world should see the new records. In practice, Cloudflare DNS is very fast to update.

---

![man reading papers in front of computer](https://images.unsplash.com/photo-1576669801775-ff43c5ab079d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDQ1fHx0ZXN0aW5nfGVufDB8fHx8MTc0ODk3NzAyMHww&ixlib=rb-4.1.0&q=80&w=2000)

Photo by [National Cancer Institute](https://unsplash.com/%40nci?ref=kerryhatcher.com) / [Unsplash](https://unsplash.com/?utm_source=ghost&utm_medium=referral&utm_campaign=api-credit)

### 4. Testing and Verification

With DNS configured, let’s test everything:

* **MX Lookup:** Use a tool like **MXToolbox** (mx toolbox dot com) to perform an *MX lookup* on your domain. It should list the Fastmail (Messaging Engine) servers as your MX, in the correct priority order. If you see those, your MX is set. If not, recheck the entries.
* **SPF Check:** MXToolbox also has a *SPF record lookup* tool. Enter your domain, and it will fetch and validate your SPF. You want it to say SPF Found, and likely it will parse it showing the include for Fastmail’s servers. If there’s a syntax error, fix it (SPF must be a single string starting with `v=spf1`).
* **DKIM Verify:** DKIM is a bit harder to test via DNS alone because it’s a public key. However, you can use tools: some websites let you enter a domain and selector to retrieve the DKIM key (MXToolbox has a DKIM lookup where you provide selector and domain). For example, test `fm1._domainkey.yourdomain.com` – it should retrieve a public key string (if using Fastmail’s, it might redirect, but usually works). Alternatively, the real proof is when you send an email and see a DKIM-Signature header. So for now, ensure the records exist in Cloudflare with the correct names.
* **DMARC Validate:** You can use a DMARC inspector tool (MXToolbox has one for DMARC as well). It will show your policy. Initially, if it’s `p=none`, the tool might just say “monitoring only”. That’s fine. The presence of a DMARC record is the key first step.
* **Send Test Emails:** Now configure your email account on Fastmail (or your chosen provider) to use your domain. In Fastmail, you’d add the domain in their admin settings (if you haven’t already) and they’ll check those DNS records. Fastmail’s domain setup wizard actually flags if something is missing. Once Fastmail knows about your domain and your user is set to send from it, try sending an email to another account (like a Gmail or Outlook account you have access to). When it arrives, view the email headers (in Gmail, “Show original” to see headers). Look for `Received-SPF: pass`, `DKIM: pass`, and `DMARC: pass` in the headers. Gmail, for instance, will say something like “spf=pass (google.com: domain of you@yourdomain.com designates X as permitted sender) ... dkim=pass ... dmarc=pass”. This indicates all the auth mechanisms are working! Additionally, the *From:* should show your custom address.
* **Webmail and Client Test:** Send an email *to* your new address as well (from some other account) to verify you can receive mail. Check via Fastmail’s web interface or your email client. If something’s misconfigured with MX, you might not receive, but if the MX is right, it should come through. Also test sending from your new address to, say, your friend’s email and ask if it landed in Inbox (and not spam). With proper SPF/DKIM, a reputable provider like Fastmail, and a custom domain, you’re likely to have very good deliverability out of the gate.
* **Troubleshooting:** If any of the checks fail, revisit Cloudflare’s DNS settings. Common issues include: typos in the domain names (e.g., missing a dot in CNAME targets, which Cloudflare might interpret as a relative name), forgetting to change nameservers (so you were editing records on Cloudflare that aren’t actually live), or propagation delays (rare with Cloudflare’s low TTL). MXToolbox’s *Diagnose* tool or “All DNS” check can be handy; it will report if, say, your domain has no DMARC or if your SPF doesn’t include the sending IP.

Finally, once everything is working, you can gradually ramp up your DMARC policy if you want to enforce it. Set `p=quarantine` for a while (to send failures to spam) and eventually `p=reject` (to outright reject unauthorized senders) once you’re confident only your provider sends mail for your domain. This helps prevent spoofers from abusing your domain in phishing, etc. Don’t forget to monitor any DMARC reports sent to your rua address (there are free services to aggregate these reports into a readable format).

### Wrapping Up

You’ve now reclaimed control of your email by using a private email provider and your own domain! The combination we used here – Fastmail + Cloudflare DNS – is just one example. It provides an excellent mix of usability, security, and privacy. Fastmail handles the mail service professionally (no fuss about uptime or spam filtering on your end), and Cloudflare ensures your DNS is fast and globally resilient.

Equipped with your custom domain email, you project professionalism and you’re shielded from many privacy pitfalls of free email services. No longer can a giant corporation rifling through your correspondence for ad data – you’ve chosen a service that respects your privacy. And if circumstances change, you can move to a new host without changing that all-important email address you’ve used for years. In the long run, this setup future-proofs your email communications.

Remember, the tech world is ever-evolving. It’s good to stay informed on developments like new authentication standards (e.g., BIMI for brand logos in email, or updates to DMARC), as well as your email provider’s feature updates. But the foundation you’ve set up – **email on your own domain with a privacy-first provider** – will serve you well for years to come. Happy emailing, on *your* terms!

## Sign up for Kerry Hatcher

My personal ramblings and advice on technology, adventure, and life

Subscribe

Email sent! Check your inbox to complete your signup.

No spam. Unsubscribe anytime.
