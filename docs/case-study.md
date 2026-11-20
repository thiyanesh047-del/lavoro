# Lavoro: case study (for the Framer portfolio)

Fields: Title "Lavoro" · Slug "lavoro" · Status Draft · Tag 1 "AI Product Design" · Tag 2 "Job Search" · Date 2026-11-20 ·
Client "Own Product" · Preview https://github.com/thiyanesh047-del/lavoro

## About

Lavoro is a job-search assistant that runs on your own computer. Each morning it reads the job boards of companies that are hiring, scores every new role against your CV, finds the person who leads the team, and drafts a short email to them. You read the email, change what you like, and send it yourself.

It is free and open source. It runs on your own Claude plan, so there is no API key to buy and no account to make, and everything it finds stays on your computer.

I designed and built Lavoro end to end: the product, the interface, the data pipeline and the code.

Find the role, and who to write to.

## Challenge

Applying through job boards means filling in the same forms again and again and hearing nothing back. An application joins a pile; a short, specific email to the person who leads the team gets read. But finding open roles that fit, and the right person behind each one, takes hours every day.

The hard part was trust. A tool that writes to strangers for you can easily embarrass you. So Lavoro only drafts and never sends. It never invents a fact about you or the role, never scrapes LinkedIn or logs in anywhere, and labels every email address by how sure it is: listed in the ad, published online, verified, or guessed and worth checking.

## Process

I started from my own job search in Stockholm and from studying how other job tools work: what they get right, and where they ask for blind trust. Then I mapped the loop a job seeker actually runs every day and built Lavoro around it:

1. Read roles straight from the companies' own job boards (Greenhouse, Lever, Ashby, Workable, Workday, SAP SuccessFactors and more, plus Sweden's Platsbanken).
2. Score each role against the CV, with the reason in plain words.
3. Find who hires, one person per team, only when asked.
4. Draft a short email in the candidate's own voice, from facts in their profile only.

The interface went through several rounds. I redesigned the welcome and role pages to give Lavoro its own identity: a calm layout with the CV box on the left and a real example of the result on the right, Lavoro's own serif typeface, and a pale dawn palette with a single rose accent. I checked every page on desktop and at phone width, and wrote a terms and privacy page that states exactly what leaves the computer and where it goes.

## The product

Today shows the roles that fit best, each with its fit score and a ready email. All jobs lists every open role from the job boards Lavoro reads, filtered by kind of work, place, pay or visa support. Company pages group open roles by team and add a "Who to write to" sheet: one person per team, found on request, with the draft right there to open in Gmail. Role pages show what a role pays and which skills the ads ask for.

## Result

Lavoro is open source on GitHub and is built to run every morning on your own computer. A typical run reads around 27,000 open roles at about 1,500 companies. It never sends an email itself, so the person stays in control of every message.
