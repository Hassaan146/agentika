# Week 4 — Prompt Log

All prompts given during Week 4 are recorded here. This file is updated on every push.

---

## 2026-07-13

> make a week 4 branch, add prompts.md to it, also maintain my prompts and automatically add it to the prompts.md at every push
>
> • What are AI agents? Agents vs chatbots vs copilots • Agent architecture: planner → executor → memory loop • Skills (tools/functions): defining and registering callable skills • Function calling with Claude API and OpenAI-compatible APIs • Hooks: pre/post-action interceptors in agent pipelines • Memory types: in-context, vector (ChromaDB), key-value stores • Plugins: extending agents with search, code execution, file I/O • Multi-step reasoning: chain-of-thought, ReAct pattern • Intro to LangChain & LlamaIndex (agents & retrieval) • Agentic coding tools survey: Cursor, Windsurf, Claude Code
>
> These are the concepts of week 4. I want to learn all these topics conceptually. Make a markdown file in which all of these topics are explained conceptually and examples are present. Also, you can use documentation or anything, but I want to get conceptual clarity of all of these topics.
>
> add this prompt too to the week 4 prompts.md

---

> [Screenshot of Week 4 task list: ✅ Build a research agent with a web-search skill (SerpAPI / Brave) ✅ Add memory: agent recalls facts from earlier in the session ✅ Implement a hook that logs every tool call with timestamps ✅ Add a file-read plugin: agent can read .txt / .pdf files ✅ Demo: single agent answers multi-hop questions using all of the above ✅ Update prompts.md]
>
> This is my week 4 tasks, I want to keep things simple but do all the things, provide a detail constructed plan and make a plan.md and make a progress.md as well, and push them to github, when i approve then we will start working on it

*Follow-up review feedback on the first plan draft (summarized): memory oversimplified & modeled as tools instead of internal architecture; no tool-registry abstraction; hooks underutilized (should validate, time, collect metrics); logging lacked args/duration/status; weak error handling; no retry mechanism; search behavior underspecified (snippets vs page content); file-reader security gaps (path traversal, file types, size); multi-hop demo too search-only; no prompt-design documentation; no structured output schemas (Pydantic); config not centralized; no testing strategy; hardcoded step limit; limited extensibility; no justification for custom-vs-LangChain; no architecture diagram. → Plan revised to rev 2 addressing all points.*

---

> now start executing the plan, i will rotate the api keys laterly, keep them in .env
> groq: [key shared privately — kept in .env, gitignored]
> brave: the website is down so serp api, revise the plan.md and also write the reason
> [serpapi key shared privately — kept in .env, gitignored]
> start working and test it completely before providing me

---

> did u add linting config ruff in it ?

---

> add this in the promots.md and commit push

---

> how can i run this?
> dont you think i should make a front end of this ?
> just tell me but first tell me what are the docs for and how can i use my agent

---

> is there any option for the previous chat memory?

---

> ok so the prompt i am giving to you and all the next prompts i give u add this to prompts.md and keep updating it
>
> HERO SECTION CREATION PROMPT
>
> Create a modern hero section with a looping video background and the following specifications:
>
> Video Background: URL: https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260329_050842_be71947f-f16e-4a14-810c-06e83d23ddb5.mp4 — Size: 115% width and height — Position: Centered horizontally, anchored to top with object-top focal point
>
> Custom JavaScript fade system (NO CSS transitions): 250ms requestAnimationFrame-based fade-in on load/loop start; 250ms fade-out when 0.55 seconds remain before video end; fadingOutRef boolean prevents re-triggering fade-out from repeated timeUpdate events; On ended: opacity set to 0, 100ms delay, reset to currentTime = 0, play, fade back in; Each new fade cancels running animation frames to prevent competing animations; Fades resume from current opacity (no snapping)
>
> Fonts Required: Schibsted Grotesk, Inter, Noto Sans, Fustat (weights: 400, 500, 600, 700)
>
> Navigation Bar: Logo "Logoipsum" (Schibsted Grotesk SemiBold, 24px, -1.44px tracking); Menu items: Platform, Features (dropdown chevron), Projects, Community, Contact; Right side: "Sign Up" (transparent, 82px), "Log In" (black bg, white text, 101px); Padding: 120px horizontal, 16px vertical
>
> Hero Content (moved up 50px): Badge (dark badge with star icon + "New", light bg "Discover what's possible", Inter 14px, rounded + shadow); Headline "Transform Data Quickly" (Fustat Bold, 80px, -4.8px tracking, black, centered); Subtitle "Upload your information and get powerful insights right away..." (Fustat Medium, 20px, #505050, max-width 736px)
>
> Search Input Box: Backdrop blur, rgba(0,0,0,0.24), 728px max-width, 200px height, rounded 18px; Top row credits: "60/450 credits" + green "Upgrade" button, right: AI icon + "Powered by GPT-4o" (Schibsted Grotesk Medium 12px white); Main input: white bg rounded 12px shadow, placeholder "Type question..." (16px), black circular submit button with up arrow (36px); Bottom row: Attach/Voice/Prompts buttons (gray, rounded 6px), right: "0/3,000" counter
>
> Icons: chevron down, up arrow, star, AI sparkle, paperclip, microphone, search
>
> Spacing: nav→hero 60px; header→search 44px; within header 34px; hero up 50px; horizontal padding 120px
>
> Colors: black #000000, gray #505050, light gray #f8f8f8, green rgba(90,225,76,0.89), dark badge #0e1311, white #ffffff, overlay rgba(0,0,0,0.24)
>
> Component Structure: VideoBackground with custom fade logic; nav bar; hero content container; nested badge/header/search components; all over full-screen video
>
> this is the page, remove the attach voice and prompts option, remove the header/dashboard, just add the liveness of the website it moves through the mountains or the valleys, just just use the typing form the ui ux pro max skills, also remove this [credits bar / Powered by GPT-4o], on the top left instead of lorum ipsum write Agentika, also this should be single page, the replies must be below it or like u love it, like the chat gpt, it goes to the mid top right and the replies on the right, and use glass-morphism, the replies should also be by using the typing form the ui-ux skills, unique fonts and use colors like green and white to match the vibe, for the glass-morphism use a blurry thing not too glassy but it should look good, no extra thinks other than this in the front end, only one route, use prettier and linting if you think

---

> add the logo of agentika to icon.svg, why is this, correct this, the video is looping when the clip ends in the background there is a a whole whittish effect remove that commit and push, also update prompts.md

---

> are u using the professional git commit techniques?

---

> [screenshot: green outline box around the search input] correct this, and always use industry style commit techniques, ive always told u!, save this in memory for other sessions and new sessions

---

> [screenshot: composer overlapping hero subtitle] the writing box is overlapping the text written, move the background text a bit upwards so it should not overlap, do this and the same loop, commit push but professional commits pls

---

> [screenshot: reply bubble showing "Something went wrong on the server: BadRequestError. Please try again."] how to deal with this, is this optimal? when something happens, then dont tell the user this, tell him that limit is hit, use typography and good colors so it should look good, commit push

---

> did u commit pushed it with professional commit and update prompts.md and progress.md? add this prompt too in the .md file

---

> run it for me

---

> now i am opening the code explain the whole code to me, explain three things whats, hows and why

---

> is it the complete understanding? does it covers complete understanding of the code, backend only?

---

> give me complete understanding so like previously i cant be blank, make a complete explanation including the whats hows and whys and other things. make a markdown file, of this, update the prompts.md and push it to both arbisoft week 4 branch and agentika repositories

---

> i want you to push the complete week 4 code and all the markdown files associated with it to https://github.com/Hassaan146/agentika this repo in the main, and make a commit
