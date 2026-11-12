# Saying this out loud

Short sentences on purpose. Under 12 words each. Losing a word costs you a few words, not a paragraph.

---

## 15 seconds, when he asks what it is

It finds four specific mistakes in code that calls an AI model.

It reads the structure of the code, not the text.

No model, no API key. It costs nothing and gives the same answer every time.

---

## 45 seconds, the full version

It finds four specific mistakes in code that calls an AI model.

All four are mistakes I made myself and fixed.

One example. The model sends back a reply in blocks.

Most code reads the first block and assumes it is text.

Turn on extended thinking and the first block is not text. The code crashes.

Another one. Building a new client every time you call the API.

That opens a new connection on every single request.

I wrote that bug in April. I fixed it. Then I wrote it again in October.

The tool reads the syntax tree. That is the structure Python builds from your code.

A text search cannot do this. It does not know what a function is.

So it cannot tell you whether a line sits inside one.

And there is no AI model in it. These are exact questions with exact answers.

That makes it free, and it gives the same answer every run.

---

## The part worth telling, if he gives you room

The first thing I pointed it at was my own code.

It found a real bug in a project I had called finished the day before.

The same mistake I had fixed somewhere else in April.

Then it told me the tool itself was wrong.

It flagged five problems. Four of them were not problems.

My rule asked whether the client was built inside a function.

The real question is whether it is built inside something that runs repeatedly.

A startup function runs once. That is fine. My rule did not know the difference.

So I narrowed the rule. Then I wrote tests for every wrong answer it had given.

Thirteen tests now. The CI runs the scanner against its own code.

---

## If he asks what the result is

I have not published a number yet, and that is deliberate.

The scanner was right one time in five on its first run.

So before any number goes out, I read thirty hits by hand.

That gives me how often the scanner is right.

A count from a tool nobody has checked is a guess with a decimal point.

---

## The other thing that broke, if the conversation goes there

I needed a fair sample of repositories, not whatever ranked first.

So I split them into four groups by star count.

I wrote the query. It ran. It returned results.

The results were nonsense. Two of the four groups came back empty.

It turns out you cannot filter code search by stars.

GitHub accepts that filter and ignores it. Nothing errors. Nothing warns.

The total said one point seven million files. My four groups summed to sixty-seven.

I only noticed because empty looked wrong.

I moved it to repository search, where that filter is real.

That changed what I am measuring, so I wrote that down too.

---

## Words to avoid saying, and what to say instead

| avoid | say |
|---|---|
| AST | the syntax tree, the structure Python builds from your code |
| static analysis | reading the code without running it |
| false positive | it flagged something that was not a problem |
| precision | how often the tool is right when it flags something |
| stratified sample | split into four groups by star count |
| dogfooding | I pointed it at my own code first |
| stdlib | built into Python already |

---

## If a word goes missing

Pause. Two seconds of silence is invisible on a call.

Then say one of these and start a new short sentence:

- Let me say that a different way.
- The short version is this.
- Give me one second.

Do not try to rescue the sentence you lost.

If the word is gone, describe the thing. "The part that reads the code" works fine.
