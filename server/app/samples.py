import datetime as dt
import hashlib
import random
import secrets
import time
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import models, scheduling

TZ = "America/Los_Angeles"
SECRETARY = "Kevin"
ADVISOR = "Dr. Quinn Harper"
OFFICERS = [("Alex Rivera", "President"), ("Jordan Lee", "Vice President"), ("Sam Ortiz", "Treasurer")]
SENATORS = ["Taylor Kim", "Casey Morgan", "Riley Chen", "Avery Patel", "Morgan Diaz", "Jamie Brooks", "Drew Nguyen",
            "Parker Shah", "Reese Alvarez", "Skyler Grant", "Emerson Cole", "Hayden Brooks-Ali", "Rowan Ellis"]
GUESTS = [("Maria Lopez", "the Transfer Center"), ("Devon Wright", "Student Health Services"),
          ("Priya Raman", "the Library"), ("Marcus Hill", "Campus Safety"), ("Elena Park", "Financial Aid"),
          ("Omar Haddad", "the Career Center"), ("Grace Kim", "Facilities"), ("Luis Ortega", "Student Life")]
LENGTHS = {"short": (12, 20), "standard": (35, 55), "long": (75, 110)}
PROJECTS = [
    ("Trunk or Treat", "candy, decorations, and a photo booth"), ("Spring Club Rush", "tables, tents, and flyers"),
    ("Food Pantry Drive", "shelf-stable food and reusable bags"), ("Mental Health Awareness Week", "a guest speaker and stress kits"),
    ("Voter Registration Day", "a registration table, buttons, and snacks"), ("Finals Week Snack Bar", "coffee, fruit, and granola bars"),
    ("Transfer Fair", "booth rentals and printed guides"), ("Earth Day Cleanup", "gloves, grabbers, and volunteer lunch"),
    ("Lunar New Year Celebration", "decorations, lanterns, and performers"), ("Career Closet", "racks, hangers, and dry cleaning"),
    ("Welcome Week BBQ", "food, a sound system, and canopies"), ("Hispanic Heritage Month Mixer", "catering and a DJ"),
    ("Veterans Day Breakfast", "breakfast for 80 and table decorations"), ("Study Abroad Info Night", "pizza and printed brochures"),
    ("Movie Night on the Quad", "a projector rental, screen, and popcorn"), ("Women in STEM Panel", "speaker gifts and refreshments"),
    ("Pride Week Kickoff", "a banner, pins, and a photo wall"), ("Black History Month Showcase", "performer stipends and staging"),
    ("Blood Drive", "volunteer shirts and snacks for donors"), ("Commencement Reception", "catering and graduation stoles"),
]
ISSUES = [
    ("library hours during finals", "the Library", ["keep the library open until midnight", "add Saturday hours",
     "open the group study rooms earlier"], ["staffing costs", "security after 10 p.m.", "student worker schedules"]),
    ("the parking permit price increase", "Parking Services", ["ask for a student discount", "push for a payment plan",
     "expand the free evening lot"], ["the district's budget gap", "the construction on Lot C", "commuters with early classes"]),
    ("cafeteria prices", "Food Services", ["add a five-dollar meal option", "accept the food pantry vouchers",
     "survey students on menu prices"], ["the vendor contract", "rising food costs", "students with dietary needs"]),
    ("Wi-Fi dead zones in the science building", "IT Services", ["add access points on the second floor",
     "post a map of strong signal areas", "open the computer lab longer"], ["the install timeline", "funding from the tech fee", "lab disruptions"]),
    ("the safety escort service", "Campus Safety", ["extend escort hours to 11 p.m.", "add a text-to-request option",
     "put up more signs about the service"], ["officer staffing", "response times", "lighting in the north lots"]),
    ("counseling wait times", "Student Health Services", ["add a drop-in hour", "partner with a telehealth provider",
     "train peer listeners"], ["confidentiality", "the cost per session", "after-hours coverage"]),
    ("textbook costs", "the Academic Senate", ["push for more free online textbooks", "start a textbook lending shelf",
     "survey faculty about required editions"], ["faculty buy-in", "copyright limits", "access codes for online homework"]),
    ("the free bus pass program", "Student Life", ["renew the pass for next year", "add the weekend routes",
     "promote it at orientation"], ["the contract renewal date", "ridership numbers", "the cost per pass"]),
    ("accessible entrances", "Facilities", ["fix the automatic door at the gym", "add a ramp by the theater",
     "map accessible routes for the website"], ["the repair backlog", "ADA compliance deadlines", "temporary fixes"]),
    ("club funding rules", "the Budget Committee", ["raise the per-club cap", "allow co-sponsored events",
     "require receipts within two weeks"], ["fairness for small clubs", "end-of-year leftover funds", "late reimbursements"]),
    ("the attendance policy in the bylaws", "the Bylaws Committee", ["allow two excused absences", "count virtual attendance",
     "add a removal warning step"], ["quorum problems", "students with jobs", "how absences get recorded"]),
    ("the spring election timeline", "the Elections Committee", ["open filing a week earlier", "add an online candidate forum",
     "extend voting to three days"], ["candidate turnout", "campaign rules", "ballot accessibility"]),
    ("food pantry hours", "Basic Needs", ["open the pantry on Fridays", "add an evening shift", "start a pre-order form"],
     ["volunteer coverage", "storage space", "privacy for students using it"]),
    ("charging stations in the cafeteria", "Facilities", ["install four charging kiosks", "add outlets along the window counter",
     "lend portable chargers at the front desk"], ["electrical work costs", "theft", "where cords would run"]),
]
STATS = ["{n} students signed the petition", "about {pct} percent of the survey said it was a problem",
         "we got {n} comments about it on the suggestion form", "{pct} percent of the students I asked had dealt with it",
         "the last report showed {n} incidents this semester", "attendance on that went up {pct} percent last year"]
OPENERS = ["I added {issue} to the agenda because a lot of students have brought it up.",
           "I want to talk about {issue}. It keeps coming up at our tabling events.",
           "Can we spend a few minutes on {issue}? I met with {office} about it last week.",
           "{issue_cap} has been on my list since the start of the semester, so I wanted to give an update."]
OPINIONS = ["I think we should {option}. It helps the most students for the least money.",
            "My concern is {concern}. We should hear from {office} before we decide.",
            "What if we {option} as a trial for {weeks} weeks and then look at the numbers?",
            "{office} told me they're open to it if we {condition}.",
            "I'd rather we {option}. The other ideas depend on {concern}, and that could take all year.",
            "Honestly, {concern} is the biggest problem here. Whatever we do has to deal with that first.",
            "I talked to a few students in my classes, and they mostly want us to {option}."]
CONDITIONS = ["share the cost", "send a formal letter", "show real student demand", "bring it to shared governance first",
              "help with the outreach", "give them a few weeks to look at the budget"]
FOLLOWS = ["Who wants to reach out to {office} about this?", "Should we form a small working group on {issue}?",
           "Can someone draft a letter we can review next meeting?", "Do we have a deadline we're working toward?"]
TAKES = ["I can do that and report back by {day}.", "I'll take it. I already have a contact there.",
         "Put me down. I'll send an update in the group chat by {day}.", "I can help {name} with that."]
REPORTS = ["{event} had about {n} students come through, which is {cmp} than last year.",
           "We spent {money} of the {money2} we budgeted for {event}, so we came in under.",
           "I met with {office} about {issue}. They're going to send numbers by {day}.",
           "The {club} asked us to co-sponsor {event} in {month}. I told them we'd discuss it.",
           "Our social media posts reached about {n} people this month, mostly on Instagram.",
           "Tabling at the {place} went well. We signed up {n} new volunteers.",
           "I'm still waiting on {office} to confirm the room for {event}.",
           "Reminder that the {month} budget requests are due on {day}.",
           "I attended the district meeting on {issue}. The short version is nothing is decided yet.",
           "We have {n} open committee seats, so please send anyone interested my way."]
CLUBS = ["Robotics Club", "Black Student Union", "Gaming Club", "Nursing Club", "Latinx Student Alliance",
         "Veterans Club", "Art Club", "Psychology Club", "Hiking Club", "Coding Club"]
PLACES = ["Student Center", "library lawn", "cafeteria", "quad", "science building lobby"]
VENDORS = ["Party City", "Costco", "the campus bookstore", "Smart & Final", "a local print shop", "Home Depot", "Amazon",
           "a family-owned caterer", "the district warehouse"]
FUND_QA = [
    ("Did we get more than one quote for {event}?", ["Yes, {vendor} quoted {money} and {vendor2} quoted {money2}, so we went with the lower one.",
     "We got three quotes. {vendor} was the cheapest by about {money}.", "Two so far. {vendor2} is still getting back to us."]),
    ("Is {event} coming out of the events line or the general fund?", ["The events line. After this there's about {money2} left in it.",
     "The general fund, since the events line is almost out.", "Half from each, based on what Sam suggested last week."]),
    ("How many students do we expect at {event}?", ["Around {n}, based on the sign-ups so far.", "Last year we had about {n}, so we planned for a few more.",
     "Hard to say, but the interest form has {n} responses already."]),
    ("Where will the {event} supplies be stored afterward?", ["In the ASG storage closet. Facilities already said that's fine.",
     "The {club} has space in their room, and they offered.", "Most of it gets used up, and the rest goes to the next event."]),
    ("Do we need a food permit for {event}?", ["No, the caterer covers that. We just turn in the event form by {day}.",
     "Yes, and we already applied. It should come back by {day}.", "Not for prepackaged snacks, which is all we're serving."]),
    ("Can we split the cost of {event} with another club?", ["The {club} offered to cover about {money}, so it's already split.",
     "We asked the {club}, and they're checking their budget.", "Not this time, but we can ask for the next one."]),
    ("Is there a cheaper option for {event} we haven't looked at?", ["We looked at {vendor}, but they couldn't deliver on time.",
     "We could borrow some things from Student Life, which would save about {money}.", "This is already the cheapest one that meets the requirements."]),
    ("What happens with {event} if it rains?", ["We have the cafeteria reserved as a backup.", "We'd move it to the gym. It's already on hold.",
     "We'd postpone it a week and keep the same vendors."]),
    ("How many volunteers does {event} need?", ["About {n2} for setup at {hour} and a few more for cleanup.",
     "{n2} total, split into two shifts.", "We have {n2} signed up and need a few more."]),
    ("How are we promoting {event}?", ["Instagram, the campus newsletter, and tabling at the {place} the week before.",
     "Flyers in every building and announcements in classes.", "The {club} is helping us post it, and we'll table at the {place}."]),
    ("Is {event} accessible for students with disabilities?", ["Yes, it's on the ground floor and we'll have seating and captions.",
     "We checked with the accessibility office and they signed off.", "Yes, and we're adding an ASL interpreter for the main part."]),
    ("When do we need the money for {event} by?", ["The vendor needs payment by {day}, so we're asking today.",
     "By the end of the month, but earlier gets us a discount.", "Next {day}, so this is our last meeting before then."]),
]
FUND_VIEWS = ["I support {event}. It always brings a big crowd.", "I'm fine with {event} as long as we get receipts this time.",
              "Could we trim {event} a little and still make it work?", "{event} is a good use of the events budget.",
              "I'd like to see last year's numbers for {event} first.", "We should make sure the {club} gets credit for {event} too.",
              "If {event} is accessible and free for students, I'm in.", "Can we promote {event} in classes too?"]
GUEST_LINES = ["This semester {office} has helped about {n} students.", "One thing we're working on is how to {option}.",
               "The biggest challenge for us right now is {concern}.", "We're seeing about {pct} percent more students than last year.",
               "If your members want to help, the best thing is to {condition}.", "We just hired {n2} new student workers to keep up.",
               "Our survey last month got {n} responses, and {issue} was near the top."]
GUEST_QA = [("How can students find out about {office}?", ["It's on our website, and I'll send you a flyer for your social media.",
             "Most students hear from their counselor, but we want to do more outreach.", "We table every Tuesday at the {place}."]),
            ("Is there a cost for students at {office}?", ["No, it's free for enrolled students.", "Most things are free; a few workshops have a small fee.",
             "It's covered by the student fee you already pay."]),
            ("What hours is {office} open?", ["Monday through Thursday until {hour}, and Fridays until noon.",
             "Weekdays from 8 to 5, with evening hours on Wednesdays.", "We just added Saturday hours this semester."]),
            ("Can we share {office}'s flyer?", ["Of course, please share it everywhere.", "Yes, I'll email it to Kevin after the meeting.",
             "Please do. I'll send a version sized for Instagram."]),
            ("Does {office} take walk-ins?", ["Yes, but appointments are faster during midterms.", "Only in the mornings right now.",
             "Yes, any time we're open."]),
            ("How can ASG help {office} the most?", ["Honestly, getting the word out. Most students don't know we exist.",
             "Sharing our surveys would help a lot.", "Inviting us to events like this one."])]
COMMITTEES = ["Events Committee", "Budget Committee", "Outreach Committee", "Bylaws Committee", "Sustainability Committee",
              "Elections Committee", "Basic Needs Committee"]
COMMITTEE_LINES = ["The {committee} met on {day} with {n2} members. We mostly worked on {event}.",
                   "The {committee} is drafting a proposal on {issue} and will bring it next meeting.",
                   "The {committee} needs {n2} more volunteers for {event}.",
                   "The {committee} reviewed {n2} funding requests and recommends approving most of them.",
                   "The {committee} sent a survey about {issue} and got {n} responses so far."]
COMMENTS = ["Hi, I'm a student here. I wanted to bring up {issue}. I really hope ASG can {option}.",
            "Hi everyone. {issue_cap} has been hard for a lot of us because of {concern}.",
            "Thanks for having public comment. Could ASG talk to {office} about {issue}?",
            "I'm a first-year student. I didn't know about {issue} until this week, and I think more students should hear about it."]
ANNOUNCE = ["Next meeting is {day} at 2 p.m. in the {place}.", "Volunteers are still needed for {event}; sign up in the group chat.",
            "Office hours this week are {day} from noon to 2.", "The {club} is hosting an open house on {day}, everyone's invited.",
            "Don't forget the {month} budget requests are due on {day}.", "Photos from {event} are up on our Instagram.",
            "The {committee} meets {day} at 3 if you want to join."]
CHATS = ["Can everyone see the slides?", "Here's the budget sheet link: https://example.edu/budget", "Sorry, my connection keeps dropping.",
         "Is there a sign-up sheet for {event}?", "I can help with {event}!", "Running {n2} minutes late, sorry.",
         "Can someone repeat the amount?", "+1 to what {name} said", "Is this meeting being recorded?"]
TANGENTS = [("Did anyone else get the parking permit email this morning?", "Yeah, they moved the deadline to Friday."),
            ("Sorry, is the Wi-Fi slow for everyone or just me?", "It's slow in the Student Center too."),
            ("Real quick, is there still pizza in the back?", "Only veggie left."),
            ("Can we turn the AC down a little? It's freezing in here.", "I'll ask facilities after."),
            ("Did the bookstore ever restock the blue books?", "Not yet, I checked yesterday."),
            ("Whose water bottle is this on the table?", "Oh, that's mine, sorry.")]
GLITCHES = [("You're on mute.", "Sorry, can you hear me now?"), ("Your audio cut out for a second.", "Let me move closer to the router."),
            ("Can whoever has the echo mute themselves?", "Sorry, that was me.")]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
MONTHS = ["October", "November", "February", "March", "April"]
MISHEARD = ["Kevan", "Kevine", "Kevin"]


def money(n):
    return "${:,.0f}".format(n)


FUND_MORE = [
    ["For {event} we compared {vendor} and {vendor2}; {vendor2} was cheaper but couldn't do the date.",
     "Only one so far for {event}. The other vendor never called back."],
    ["{event} is coming from the events line, and it still leaves room for the rest of the semester.",
     "We split {event} between the events line and outreach, since it's partly a recruiting event."],
    ["For {event} we're planning on about {n}, since it's during the lunch hour.",
     "The {event} sign-up sheet is at {n} so far, and it usually doubles in the last week."],
    ["Everything from {event} fits in the two bins we already have in the closet.",
     "The {event} banners can be reused, so we'll keep those in the Student Life office."],
    ["{event} only has packaged food, so the event form covers it.",
     "We checked with the cafeteria, and {event} doesn't need a separate permit."],
    ["The {club} said they'd put in {money} toward {event} if their logo goes on the flyer.",
     "For {event}, the Veterans Club is helping with setup instead of money."],
    ["We priced {event} three different ways, and this was the lowest that still works.",
     "We could cut the decorations for {event}, but that only saves about {money}."],
    ["If it rains, {event} moves to the {place}. We already have it on hold.", "{event} is indoors, so weather isn't an issue."],
    ["For {event} we need {n2} people at {hour} and a smaller group for cleanup.",
     "{event} needs about {n2} volunteers. The Outreach Committee is covering half."],
    ["For {event} we're doing flyers, an Instagram post, and announcements in a few classes.",
     "The {club} is sharing {event} with their members, and we're tabling at the {place}."],
    ["{event} is in a ground-floor room, and we'll have captions on the slides.",
     "We asked the accessibility office to look at the {event} layout, and they said it's fine."],
    ["The deposit for {event} is due {day}, so we need the vote today.", "We need the {event} money by the end of next week."],
]
GUEST_MORE = [
    ["The best way to find {office} is our page on the college website, or just stop by.",
     "We post {office} updates on Instagram, and we're happy to share with ASG too."],
    ["{office} doesn't charge students for anything we offer.", "Everything at {office} is covered by student fees."],
    ["{office} is open until {hour} most days, and we're adding evening hours in {month}.",
     "Hours for {office} are on the door and on the website. Fridays are shorter."],
    ["Yes, please share the {office} flyer. I'll send a digital copy.", "Of course. The {office} flyer has a QR code for appointments."],
    ["{office} takes walk-ins in the morning and appointments in the afternoon.", "Walk-ins are fine at {office}, but expect a short wait."],
    ["Honestly, telling students {office} exists is the biggest help.", "If ASG shares the {office} survey, that helps us a lot."],
]
MORE_ANSWERS = dict(zip([q for q, _ in FUND_QA], FUND_MORE))
MORE_ANSWERS.update(zip([q for q, _ in GUEST_QA], GUEST_MORE))
OPINIONS += ["For {issue}, I really think we should {option}, even if it starts small.",
             "On {issue}, the students I talk to care most about {concern}.",
             "If we go to {office} about {issue}, we should bring the survey results with us.",
             "I'm not sure we can fix {issue} this semester, but we could at least {option}.",
             "I like the idea to {option}, but we need to plan around {concern} for {issue}.",
             "Other colleges handled {issue} by trying to {option}. We could ask how it went.",
             "My friends brought up {issue} last week. They said {concern} is the real issue.",
             "Could we put {issue} in the next newsletter so students know we're working on it?",
             "For {issue}, maybe we start by asking {office} what they'd need from us.",
             "I'd support a resolution on {issue} if it asks them to {option}.",
             "We tried something on {issue} two years ago and it stalled because of {concern}.",
             "Let's not overpromise on {issue}. We can push to {option} and see what happens."]
STATS += ["{pct} percent of the students we surveyed said {issue} affects them every week",
          "{n} students mentioned {issue} on the suggestion form this semester",
          "{issue} came up at almost every tabling event, about {n} times",
          "{office} told me they get around {n} questions about {issue} a month",
          "only {pct} percent of students knew who to contact about {issue}",
          "complaints about {issue} went up {pct} percent since last year"]
OPENERS += ["I'd like to bring up {issue} again, since we didn't finish last time.",
            "A few students emailed me about {issue}, so I put it on today's agenda.",
            "{issue_cap} is something {office} asked us to weigh in on.",
            "Quick item on {issue}. I want to get a sense of where everyone stands."]
FOLLOWS += ["Can someone put together a short survey on {issue} before next meeting?",
            "Who wants to set up a meeting with {office} on {issue}?",
            "Should we invite someone from {office} to talk about {issue}?",
            "Let's have a plan for {issue} by our next meeting. Who can lead it?",
            "Can we get a written update on {issue} for the next agenda?"]
TAKES += ["I'll take {issue}. I'll email {office} tomorrow.", "I can draft the {issue} survey and share it by {day}.",
          "I'll follow up on {issue} and bring notes next week.", "Me. {issue_cap} is something I care about.",
          "I'll work on {issue} with {name}. We'll report back."]
REPORTS += ["I met with {office} on {day} about {issue}, and they want to keep talking.",
            "For {event}, we still need about {n2} volunteers. Please sign up.",
            "{event} is confirmed for {month}. The room is booked.",
            "I went to the district meeting on {day}. {issue_cap} came up there too.",
            "I followed up with {office} about {issue}. No answer yet, but I'll keep trying.",
            "Planning for {event} is on track. We have the flyer and the budget done.",
            "I sat in on the {office} meeting about {issue}. They're open to our ideas."]
GUEST_LINES += ["At {office}, the most common question we get is about {issue}.",
                "{office} is trying to {option}, but {concern} has slowed us down.",
                "Students can book time with {office} online or just walk in.",
                "{office} is hosting a workshop on {issue} in {month}.",
                "We'd love ASG's help spreading the word about {office}.",
                "Compared to last year, {office} is seeing more students ask about {issue}.",
                "{office} is short on staff right now, so wait times are longer.",
                "One idea {office} has is to {option} with ASG's support."]
COMMITTEE_LINES += ["The {committee} finished the draft on {issue}. It's in the shared folder.",
                    "The {committee} is meeting with {office} next week about {issue}.",
                    "The {committee} recommends we {option}, and we'll present details next time.",
                    "The {committee} still has {n2} open seats if anyone wants to join.",
                    "The {committee} looked at {issue} and thinks {concern} is the main obstacle."]
COMMENTS += ["Hi, I'm here about {issue}. It's been really hard because of {concern}.",
             "I'd like ASG to push {office} to {option}. A lot of us need it.",
             "Thanks for listening. {issue_cap} affects students who work and go to school.",
             "I'm in the {club}, and our members keep talking about {issue}.",
             "Is there a way students can get updates on {issue}? We never hear what happens.",
             "I wanted to say thank you for working on {issue}. Please keep going."]
ANNOUNCE += ["Club Rush sign-ups close {day}, so tell your clubs.", "The food pantry is restocked and open {day}.",
             "Spirit wear orders are due {day}.", "We're looking for a new public relations director. Applications close {day}.",
             "Midterm study snacks are in the ASG office starting {day}.", "The district student leadership conference is in {month}.",
             "Please fill out the officer availability form by {day}.", "Thank you to everyone who helped with {event}."]
SECONDS = ["It has been moved and seconded. Is there any discussion?", "Moved and seconded. Any discussion?",
           "We have a motion and a second. Discussion?", "Okay, any discussion on the motion?",
           "Is there any discussion before we vote?", "Any questions on this before we vote?",
           "It's been moved and seconded to {motion}. Any discussion?", "We have a motion to {motion}. Discussion?",
           "The motion is to {motion}. Does anyone want to speak to it?"]
CALLS = ["All in favor, say aye. Any opposed? Any abstentions?", "All those in favor? Opposed? Abstaining?",
         "Let's vote. All in favor? Any opposed?", "All in favor, raise your hand. Any opposed? Abstentions?",
         "All in favor of the motion to {motion}? Any opposed?", "Those in favor of the motion to {motion}, please say aye.",
         "Let's vote on the motion to {motion}. All in favor?"]
PASSES = ["The motion passes unanimously.", "The ayes have it. Motion carries.", "That passes unanimously.",
          "The motion to {motion} passes.", "Seeing no objections, the motion to {motion} carries.", "That's unanimous. It passes."]
FAILS = ["All in favor? All opposed? The nays have it. The motion fails.", "The motion to {motion} does not pass.",
         "That fails. We'll leave it there for now.", "The nays have it. The motion to {motion} fails."]
AMENDS = ["I'd like to amend the amount to {amount}, since we already have some supplies.",
          "Can we amend {event} down to {amount}? We have some leftover materials.",
          "I move to amend the {event} request to {amount}.", "Friendly amendment: make it {amount} for {event}.",
          "What if we did {amount} for {event} instead? We can borrow some things."]
ABSTAINS = ["I'll abstain, since I'm involved with that event.", "Abstain. I'm on the planning team.",
            "I'm going to abstain on this one.", "I abstain, since I helped write the {event} request.",
            "Abstaining. I'm one of the {event} organizers."]


IDENTITY = ("event", "office", "committee", "issue", "issue_cap", "who", "first", "motion")


class Script:
    def __init__(self, rnd, start_minute):
        self.rnd, self.t, self.start = rnd, 4.0, start_minute
        self.lines, self.chat, self.summary, self.used = [], [], {}, set()
        self.projects = rnd.sample(PROJECTS, len(PROJECTS))
        self.issues = rnd.sample(ISSUES, len(ISSUES))
        self.tangents = rnd.sample(TANGENTS, len(TANGENTS))
        self.guests = rnd.sample(GUESTS, len(GUESTS))
        self.committees = rnd.sample(COMMITTEES, len(COMMITTEES))
        self.voices = rnd.sample(ISSUES, len(ISSUES))

    def say(self, who, text):
        if text:
            self.lines.append((round(self.t, 1), who, text))
            self.t += len(text.split()) / self.rnd.uniform(2.2, 2.8) + self.rnd.uniform(1.5, 5.0)

    def type(self, who, text):
        if text:
            self.chat.append((round(self.t, 1), who, text))

    def clock(self):
        total = self.start + int(self.t // 60)
        return "%d:%02d p.m." % (14 + total // 60 - 12, total % 60)

    def values(self, extra):
        r = self.rnd
        v = {"n": r.randint(12, 480), "n2": r.randint(3, 25), "pct": r.choice(range(15, 90, 5)), "weeks": r.choice([2, 3, 4, 6]),
             "day": r.choice(DAYS), "month": r.choice(MONTHS), "club": r.choice(CLUBS), "place": r.choice(PLACES),
             "vendor": r.choice(VENDORS), "vendor2": r.choice(VENDORS), "hour": r.choice(["9 a.m.", "10 a.m.", "noon", "4 p.m.", "6 p.m."]),
             "money": money(r.choice(range(75, 2600, 25))), "money2": money(r.choice(range(300, 4000, 50))),
             "cmp": r.choice(["more", "a little more", "fewer", "about the same"]), "event": r.choice(PROJECTS)[0],
             "condition": r.choice(CONDITIONS), "committee": r.choice(COMMITTEES), "name": r.choice(SENATORS).split()[0]}
        v.update(extra)
        return v

    def key(self, template, extra):
        named = sorted((k, str(v)) for k, v in extra.items() if k in IDENTITY and "{%s}" % k in template)
        return "|" + template + repr(named)

    def line(self, pool, **extra):
        for template in self.rnd.sample(pool, len(pool)):
            key = self.key(template, extra)
            if key in self.used:
                continue
            text = template.format(**self.values(extra)).replace("..", ".")
            if text not in self.used:
                self.used.update((key, text))
                return text
        return ""

    def pair(self, pool, **extra):
        for q, answers in self.rnd.sample(pool, len(pool)):
            key = self.key(q, extra)
            v = self.values(extra)
            qt = q.format(**v).replace("..", ".")
            if key in self.used or qt in self.used:
                continue
            self.used.add(key)
            options = answers + MORE_ANSWERS.get(q, [])
            for a in self.rnd.sample(options, len(options)):
                akey = self.key(a, extra)
                at = a.format(**self.values(dict(extra, **{k: v[k] for k in extra}))).replace("..", ".")
                if akey not in self.used and at not in self.used:
                    self.used.update((qt, at, akey))
                    return qt, at
        return None


def pick(rnd, people, avoid=()):
    pool = [p for p in people if p not in avoid] or people
    return rnd.choice(pool)


def issue_args(issue, rnd=None):
    name, office, options, concerns = issue
    return {"issue": name, "issue_cap": name[0].upper() + name[1:], "office": office,
            "option": rnd.choice(options) if rnd else options[0], "concern": rnd.choice(concerns) if rnd else concerns[0]}


def vote(s, people, chair, motion, mover, seconder, outcome, roll_call=False):
    r = s.rnd
    s.say(mover, "I move to %s." % motion)
    if r.random() < 0.25:
        s.type(seconder, "Second!")
        s.say(chair, "I see a second in the chat from %s." % seconder.split()[0])
    else:
        s.say(seconder, r.choice(["Second.", "I'll second that.", "Seconded."]))
    s.say(chair, s.line(SECONDS, motion=motion) or r.choice(SECONDS[:6]))
    if outcome == "tabled":
        s.say(pick(r, people, (mover,)), s.line(["I move to table this until next meeting so we can get more information.",
                                                 "Can we table this? I'd like to see the full budget first.",
                                                 "I move to postpone this to our next meeting.",
                                                 "Motion to table until we hear back from Student Life.",
                                                 "I think we need more details. I move to table it."]) or "I move to table this.")
        s.say(pick(r, people, (mover, seconder)), r.choice(["Second.", "Seconded.", "I'll second."]))
        s.say(chair, s.line(["All in favor of tabling? Any opposed? The item is tabled.",
                             "All in favor of postponing? Opposed? It's tabled until next time.",
                             "Any objection to tabling? Seeing none, it's tabled.",
                             "Okay, all in favor of tabling? That carries. We'll bring it back next meeting.",
                             "The motion to table passes. We'll revisit it."]) or "It's tabled.")
        return "tabled"
    if roll_call:
        s.say(chair, s.line(["We'll do a roll call vote. %s, please call the roll." % SECRETARY,
                             "Let's do this one by roll call. %s?" % SECRETARY,
                             "Since this is a larger amount, we'll take a roll call vote.",
                             "%s, can you call the roll for this vote?" % SECRETARY,
                             "Roll call vote, please."]) or "Roll call vote.")
        tally = {"aye": 0, "nay": 0, "abstain": 0}
        for name in people:
            x = r.random()
            if outcome == "failed":
                x = 0.9 if x < 0.6 else x
            ballot = "aye" if x < 0.75 else "nay" if x < 0.93 else "abstain"
            tally[ballot] += 1
            s.say(SECRETARY, name.split()[0] + "?")
            s.say(name, ballot.capitalize() + ".")
        passed = tally["aye"] > tally["nay"]
        s.say(SECRETARY, "That's %d ayes, %d nays, and %d abstaining." % (tally["aye"], tally["nay"], tally["abstain"]))
        s.say(chair, "The motion %s." % ("passes" if passed else "fails"))
        return "%s %d-%d-%d" % ("passed" if passed else "failed", tally["aye"], tally["nay"], tally["abstain"])
    if outcome == "failed":
        s.say(chair, s.line(FAILS, motion=motion) or FAILS[0])
        return "failed"
    s.say(chair, s.line(CALLS, motion=motion) or r.choice(CALLS[:4]))
    if r.random() < 0.3:
        event = motion.split(" for ", 1)[-1] if " for " in motion else "that event"
        s.say(pick(r, people, (mover, seconder)), s.line(ABSTAINS, event=event) or "I abstain.")
        s.say(chair, s.line(["With one abstention, the motion passes.", "The motion carries with one abstention.",
                             "One abstention, and the rest in favor. It passes.", "That passes with one abstention."]) or
              "It passes with one abstention.")
        return "passed with one abstention"
    s.say(chair, s.line(PASSES, motion=motion) or r.choice(PASSES[:3]))
    return "passed unanimously"


def funding(s, people, chair, until):
    r = s.rnd
    if not s.projects:
        return ""
    name, what = s.projects.pop()
    amount = r.choice(range(150, 3001, 50))
    lead = pick(r, people)
    s.say(lead, "We're requesting %s for %s. It covers %s." % (money(amount), name, what))
    while s.t < until:
        qa = s.pair(FUND_QA, event=name)
        if not qa:
            break
        asker = pick(r, people, (lead,))
        s.say(asker, qa[0])
        s.say(lead, qa[1])
        if r.random() < 0.4:
            s.say(pick(r, people, (lead, asker)), s.line(FUND_VIEWS, event=name))
    final = amount
    if r.random() < 0.3:
        final = max(100, amount - r.choice([50, 100, 150, 250]))
        s.say(pick(r, people, (lead,)), s.line(AMENDS, event=name, amount=money(final)) or
              "I move to amend it to %s." % money(final))
        s.say(lead, "That works for us.")
    outcome = r.choices(["passed", "failed", "tabled"], [0.7, 0.12, 0.18])[0]
    mover, seconder = r.sample(people, 2)
    result = vote(s, people, chair, "approve %s for %s" % (money(final), name), mover, seconder, outcome, r.random() < 0.35)
    return "%s requested %s for %s (%s); motion by %s, seconded by %s, %s." % (
        lead.split()[0], money(final), name, what, mover.split()[0], seconder.split()[0], result)


def discussion(s, people, chair, until):
    r = s.rnd
    if not s.issues:
        return ""
    issue = s.issues.pop()
    name, office = issue[0], issue[1]
    lead = pick(r, people)
    s.say(lead, s.line(OPENERS, **issue_args(issue, r)))
    stat = s.line(STATS, **issue_args(issue, r))
    if stat:
        s.say(lead, "When I looked into it, " + stat + ".")
    while s.t < until:
        text = s.line(OPINIONS, **issue_args(issue, r))
        if not text:
            break
        s.say(pick(r, people, (lead,)), text)
        if r.random() < 0.35:
            s.say(lead, s.line(["Good point. {office} mentioned that too.", "I hadn't thought about that.",
                                "That's fair.", "True, I'll add that to my notes.", "Yeah, that came up in the survey too.",
                                "Agreed.", "That's a good question. I'll find out."], office=office))
        if r.random() < 0.12 and s.tangents:
            a, b = s.tangents.pop()
            s.say(pick(r, people), a)
            s.say(pick(r, people), b)
            s.say(chair, "Okay, let's get back on track.")
    s.say(chair, s.line(FOLLOWS, **issue_args(issue, r)))
    taker = pick(r, people, (chair,))
    s.say(taker, s.line(TAKES, name=lead.split()[0], **issue_args(issue, r)))
    return "Discussed %s; %s will follow up with %s." % (name, taker.split()[0], office)


def officer_round(s, people, until, advisor=False):
    r = s.rnd
    speakers = [ADVISOR] if advisor else [p for p, _ in OFFICERS if p in people] + r.sample(
        [p for p in people if p not in dict(OFFICERS)], min(3, len([p for p in people if p not in dict(OFFICERS)])))
    said = []
    for who in speakers:
        if s.t >= until and said:
            break
        text = s.line(REPORTS, **issue_args(r.choice(ISSUES), r))
        if not text:
            break
        s.say(who, text)
        said.append(who.split()[0] + ": " + text)
        if r.random() < 0.5:
            s.say(who, s.line(REPORTS, **issue_args(r.choice(ISSUES), r)))
        if r.random() < 0.3:
            s.say(pick(r, people, (who,)), s.line(["Do you need help with {event}?", "When will we know more about {event}?",
                                                   "Can you send the {event} details in the group chat?"]))
            s.say(who, s.line(["Yes, I'll send it by {day}.", "Probably by {day}.", "Any help is welcome, thank you.",
                               "I'll post it tonight."]))
    return " ".join(said[:3])


def guest(s, people, chair, until):
    r = s.rnd
    if not s.guests:
        return ""
    who, office = s.guests.pop()
    s.say(chair, s.line(["We have {who} from {office} here to give a short presentation.",
                         "Next we'll hear from {who} with {office}.", "{who} from {office} is joining us today.",
                         "Please welcome {who} from {office}.", "{who} is here to give us an update from {office}.",
                         "We invited {who} from {office} to talk with us."], who=who, office=office)
          or "Next is %s from %s." % (who, office))
    s.say(who, s.line(["Thanks for having me. I'll keep this quick and leave time for questions.",
                       "Hi everyone, thanks for the invite.", "Thank you for making time for us today.",
                       "Good afternoon. I'm happy to be here.", "Thanks. I'll go over a few updates and then take questions.",
                       "Hi, I appreciate you having me back.", "Thanks for the invitation. This will only take a few minutes."]) or "Thanks.")
    issue = next((i for i in ISSUES if i[1].lower() in office.lower()), r.choice(ISSUES))
    while s.t < until:
        text = s.line(GUEST_LINES, **dict(issue_args(issue, r), office=office))
        if not text:
            break
        s.say(who, text)
        if r.random() < 0.5:
            qa = s.pair(GUEST_QA, office=office)
            if qa:
                s.say(pick(r, people), qa[0])
                s.say(who, qa[1])
    s.say(chair, (s.line(["Thank you so much for coming, {first}.", "Thanks, {first}. That was really helpful.",
                          "We appreciate you, {first}.", "Thank you, {first}. We'll share that with students.",
                          "Thanks for the update, {first}.", "Great, thank you {first}."], first=who.split()[0])
                  or "Thank you, %s." % who.split()[0]))
    return "%s from %s presented on %s." % (who, office, issue[0])


def committee(s, people, until):
    r = s.rnd
    if not s.committees:
        return ""
    name = s.committees.pop()
    chairperson = pick(r, people)
    said = []
    while s.t < until and len(said) < 4:
        text = s.line(COMMITTEE_LINES, committee=name, **issue_args(r.choice(ISSUES), r))
        if not text:
            break
        s.say(chairperson, text)
        said.append(text)
    return said[0] if said else ""


def comments(s, chair, until):
    r = s.rnd
    said = []
    while (s.t < until or not said) and s.voices and len(said) < 10:
        issue = s.voices.pop()
        text = s.line(COMMENTS, **issue_args(issue, r))
        if not text:
            break
        s.say("Student", text)
        s.say(chair, s.line(["Thank you. We'll take that under advisement.", "Thanks for coming. We'll follow up.",
                             "We appreciate it. That's on our list.", "Thank you, we'll get back to you on that.",
                             "Thanks for sharing. Please leave your email with Kevin.", "Good point, thank you.",
                             "We hear you. That's something we've been looking into.", "Thanks. Can you stay after so we can talk more?",
                             "Thank you for coming out today.", "Appreciate it. We'll put that on a future agenda."]) or "Thank you.")
        said.append(issue[0])
    return "Students spoke about %s." % ", ".join(said) if said else ""


def run_blocks(s, makers, until, room=90):
    out = []
    while s.t < until - room:
        before = s.t
        for make in makers:
            if s.t >= until - room:
                break
            text = make(until)
            if text:
                out.append(text)
        if s.t == before:
            break
    return out


HEAVY = ("new business", "consideration", "discussion", "decision", "vote", "unfinished")
SPOKEN = ("report", "update", "presentation")


def agenda_for(slots, kind):
    agenda = slots[:]
    if not any(w in x.lower() for x in agenda for w in HEAVY):
        at = next((i for i, x in enumerate(agenda) if "announce" in x.lower() or "next meeting" in x.lower()), len(agenda))
        agenda.insert(at, "New Business")
    if kind != "special" and not any(w in x.lower() for x in agenda for w in SPOKEN):
        agenda.insert(0, "Reports")
    return agenda


def build(rnd, kind, slots, start_minute, minutes, focus=""):
    slots = agenda_for(slots, kind)
    s = Script(rnd, start_minute)
    s.agenda = slots
    main = next((p for p in s.projects if p[0] == focus), None)
    if main:
        s.projects.remove(main)
        s.projects.append(main)
    officers = [p for p, _ in OFFICERS]
    senators = rnd.sample(SENATORS, rnd.randint(5, 10))
    absent = [p for p in officers if rnd.random() < 0.15]
    people = [p for p in officers if p not in absent] + senators
    chair = next((p for p in officers if p not in absent), senators[0])
    late = people.pop() if len(people) > 5 and rnd.random() < 0.4 else ""
    voters = [p for p in people if p != chair]
    target = minutes * 60
    weights = []
    for slot in slots:
        k = slot.lower()
        heavy = any(w in k for w in HEAVY)
        weights.append(6 if heavy else 3 if any(w in k for w in ("report", "update", "public", "forum", "presentation")) else 1)
    order = s.clock()
    s.say(chair, "Okay everyone, let's get started. I call this meeting to order at %s" % order)
    if chair != officers[0]:
        s.say(chair, "%s couldn't make it today, so I'll be chairing." % officers[0].split()[0])
    s.summary["__order"] = order
    if rnd.random() < 0.35:
        a, b = rnd.choice(GLITCHES)
        s.say(pick(rnd, voters), a)
        s.say(chair, b)
    for i, slot in enumerate(slots):
        key = slot.lower()
        left = max(0, target - s.t)
        until = s.t + left * weights[i] / (sum(weights[i:]) or 1)
        s.say(chair, rnd.choice(["Next on the agenda, %s.", "Moving on to %s.", "That brings us to %s.", "Next item, %s."]) % slot)
        if "roll" in key or "attendance" in key or "quorum" in key:
            here = [chair, SECRETARY] + voters
            s.say(SECRETARY, "Present: %s." % ", ".join(here))
            if absent:
                s.say(SECRETARY, "Absent: %s." % ", ".join(absent))
            s.say(SECRETARY, "We have quorum." if len(here) >= 6 else "We do not have quorum, so we can only discuss items today.")
            s.summary[slot] = "Present: %s. Absent: %s." % (", ".join(here), ", ".join(absent) or "none")
        elif "agenda" in key and "approv" in key:
            m, sd = rnd.sample(voters, 2)
            s.summary[slot] = "Agenda approved; motion by %s, seconded by %s, %s." % (
                m.split()[0], sd.split()[0], vote(s, voters, chair, "approve the agenda", m, sd, "passed"))
        elif "minutes" in key and "approv" in key:
            if rnd.random() < 0.4:
                s.say(pick(rnd, voters), "One correction. %s's name is spelled wrong in item %d." % (
                    pick(rnd, voters).split()[0], rnd.randint(2, 9)))
                s.say(SECRETARY, "Got it, I'll fix that.")
            m, sd = rnd.sample(voters, 2)
            s.summary[slot] = "Previous minutes approved; motion by %s, seconded by %s, %s." % (
                m.split()[0], sd.split()[0], vote(s, voters, chair, "approve last meeting's minutes", m, sd, "passed"))
        elif "public" in key or "open forum" in key:
            s.say(chair, "We'll now open the floor for public comment. Please keep it to two minutes.")
            s.summary[slot] = (comments(s, chair, until) if rnd.random() < 0.85 else "") or "No public comment."
            if s.summary[slot] == "No public comment.":
                s.say(chair, "Seeing no public comment, we'll move on.")
        elif "advisor" in key:
            s.summary[slot] = officer_round(s, voters, until, advisor=True)
        elif "report" in key or "update" in key:
            parts = run_blocks(s, [lambda u: officer_round(s, voters, u), lambda u: guest(s, voters, chair, u),
                                   lambda u: committee(s, voters, u)], until)
            s.summary[slot] = " ".join(parts[:3])
        elif "unfinished" in key or "old business" in key:
            if rnd.random() < 0.6:
                s.say(chair, "We tabled this at the last meeting, so let's pick it back up.")
                s.summary[slot] = " ".join(run_blocks(s, [lambda u: funding(s, voters, chair, min(u, s.t + 240))], until)[:3])
            else:
                s.say(chair, "There's no unfinished business today.")
                s.summary[slot] = "No unfinished business."
        elif any(w in key for w in ("new business", "consideration", "discussion", "decision", "vote")):
            step = 300 if minutes >= 40 else 150
            makers = [lambda u: funding(s, voters, chair, min(u, s.t + step))]
            if kind not in ("budget", "special"):
                makers.append(lambda u: discussion(s, voters, chair, min(u, s.t + step)))
            if kind == "special":
                items = [funding(s, voters, chair, until)]
                if s.t < until - 90:
                    s.say(chair, "Before we close this item, let's talk about how it connects to other things students have raised.")
                    items += run_blocks(s, [lambda u: discussion(s, voters, chair, min(u, s.t + step)),
                                            lambda u: guest(s, voters, chair, min(u, s.t + step))], until)
            else:
                items = run_blocks(s, makers, until)
            if kind == "election":
                who = pick(rnd, voters)
                m, sd = rnd.sample([p for p in voters if p != who], 2)
                items.append("Appointment of %s as Director of Outreach %s." % (
                    who, vote(s, voters, chair, "appoint %s as Director of Outreach" % who, m, sd, "passed")))
            s.summary[slot] = " ".join(x for x in items if x)
        elif "announce" in key or "next meeting" in key:
            said = []
            while (s.t < until or not said) and len(said) < 6:
                text = s.line(ANNOUNCE)
                if not text:
                    break
                s.say(pick(rnd, voters + [chair]), text)
                said.append(text)
            s.summary[slot] = " ".join(said[:2])
        else:
            s.summary[slot] = " ".join(run_blocks(s, [lambda u: discussion(s, voters, chair, u)], until)[:2])
        if late and rnd.random() < 0.5:
            s.say(late, "Sorry I'm late, my class ran over.")
            s.say(SECRETARY, "Noting that %s arrived." % late)
            voters.append(late)
            late = ""
    if s.t < target - 120:
        s.say(chair, rnd.choice(["We still have some time, so let's open the floor for general discussion before we close.",
                                 "Before we adjourn, is there anything else people want to bring up?",
                                 "We have a few minutes left. Any other business?"]))
        extra = run_blocks(s, [lambda u: discussion(s, voters, chair, min(u, s.t + 300)), lambda u: guest(s, voters, chair, u),
                               lambda u: committee(s, voters, u), lambda u: funding(s, voters, chair, min(u, s.t + 300))],
                           target, room=60)
        s.summary["__other"] = " ".join(extra[:3])
    for i, (t, who, text) in enumerate(s.lines):
        if who == SECRETARY and rnd.random() < 0.2:
            s.lines[i] = (t, rnd.choice(MISHEARD), text)
    for _ in range(rnd.randint(1, 2 + minutes // 15)):
        text = s.line(CHATS)
        if text:
            s.chat.append((round(rnd.uniform(30, max(60, s.t)), 1), pick(rnd, voters), text))
    m, sd = rnd.sample(voters, 2)
    s.say(m, "I move to adjourn.")
    s.say(sd, "Second.")
    closing = s.clock()
    s.say(chair, "We are adjourned at %s Thanks everyone." % closing)
    s.summary["__adjourn"] = closing
    return s


def fills(s, slots):
    out = [{"under": slot, "text": s.summary[slot]} for slot in slots if s.summary.get(slot)]
    spoken = [s.summary[k] for k in getattr(s, "agenda", slots) + ["__other"] if s.summary.get(k)]
    return {"order_time": s.summary.get("__order", ""), "adjourn_time": s.summary.get("__adjourn", ""), "fills": out,
            "summary": [x for x in spoken if "motion" in x.lower()][:4]}


PERSONAL_PEOPLE = ["Alex Rivera", "Jordan Lee", "Sam Ortiz", "Taylor Kim", "Casey Morgan", "Riley Chen", "Avery Patel",
                   "Morgan Diaz", "Jamie Brooks", "Drew Nguyen"]
PERSONAL_KINDS = [("team", "Team Check-in"), ("project", "Project Planning"), ("volunteer", "Volunteer Group"),
                  ("study", "Study Group"), ("neighbors", "Neighborhood Group"), ("book", "Book Club")]
PERSONAL_FOCUS = {
    "team": [("Website Launch", "the website launch"), ("Product Demo", "the product demo"),
             ("Customer Survey", "the customer survey"), ("Newsletter Redesign", "the newsletter redesign"),
             ("Quarterly Planning", "next quarter's plan")],
    "project": [("Moving Day", "moving day"), ("Kitchen Remodel", "the kitchen remodel"), ("Summer Road Trip", "the road trip"),
                ("Family Reunion", "the family reunion"), ("App Prototype", "the app prototype")],
    "volunteer": [("Holiday Food Drive", "the food drive"), ("Park Cleanup", "the park cleanup"), ("Coat Drive", "the coat drive"),
                  ("Charity 5K", "the 5K"), ("Shelter Open House", "the shelter open house")],
    "study": [("Final Exam Prep", "the final"), ("Group Lab Report", "the lab report"), ("Statistics Midterm", "the midterm"),
              ("Capstone Presentation", "the capstone presentation"), ("Certification Exam", "the certification exam")],
    "neighbors": [("Block Party", "the block party"), ("Community Garden", "the community garden"),
                  ("Street Safety Walk", "the safety walk"), ("Yard Sale Weekend", "the yard sale"),
                  ("Holiday Lights", "the holiday lights")],
    "book": [("Next Month's Pick", "next month's pick"), ("Author Visit", "the author visit"),
             ("Summer Reading List", "the summer reading list"), ("Book Swap", "the book swap"),
             ("Library Partnership", "the library partnership")],
}
PERSONAL_TASKS = {
    "team": ["the landing page copy", "the bug list from testing", "the onboarding email", "the pricing table", "the demo script",
             "the customer interview notes", "the launch checklist", "the slide deck"],
    "project": ["the packing list", "the budget spreadsheet", "the contractor quotes", "the hotel booking", "the shopping list",
                "the schedule", "the supply order", "the shared calendar"],
    "volunteer": ["the sign-up sheet", "the flyer", "the donation boxes", "the volunteer shifts", "the thank-you cards",
                  "the supply order", "the social media post", "the route map"],
    "study": ["the practice problems for chapter 6", "the lab write-up", "the flashcards", "the slide deck", "the reading notes",
              "the study guide", "the citations", "the formula sheet"],
    "neighbors": ["the street permit", "the mailbox flyer", "the volunteer list", "the tables and chairs", "the group chat poll",
                  "the email to the city", "the cleanup supplies", "the sign-up sheet"],
    "book": ["the discussion questions", "the reading schedule", "the snack list", "the email to the library",
             "the poll for the next book", "the meeting space", "the book swap table", "the suggestion list"],
}
PERSONAL_CHOICES = {
    "team": [("the launch date", ["launch on the 15th", "push the launch to the end of the month"]),
             ("the demo format", ["do a live demo", "record a video walkthrough"]),
             ("the survey tool", ["use Google Forms", "use Typeform"]),
             ("the team lunch", ["book the Italian place", "do a potluck in the office"]),
             ("the weekly meeting time", ["keep Tuesdays at 2", "move it to Monday mornings"])],
    "project": [("the moving truck", ["rent the 15-foot truck", "hire movers for the big furniture"]),
                ("the budget", ["cap it at $2,000", "split the costs evenly"]),
                ("the date", ["go the first weekend of the month", "wait until after the holiday"]),
                ("the contractor", ["go with the cheaper quote", "go with the one who can start sooner"]),
                ("the food", ["order pizza for everyone", "have everyone bring something"])],
    "volunteer": [("the setup location", ["set up outside the library", "use the community center lobby"]),
                  ("the flyer", ["print 200 flyers", "post it online only"]),
                  ("the drop-off times", ["keep weekend drop-offs", "add a weekday evening drop-off"]),
                  ("the thank-you event", ["have a pizza night", "send thank-you cards"]),
                  ("the volunteer limit", ["cap it at 30 people", "take everyone who signs up"])],
    "study": [("the chapter split", ["split the chapters evenly", "have everyone do every chapter"]),
              ("the meeting place", ["meet in the library study room", "keep meeting on Zoom"]),
              ("the practice exam", ["do a timed practice exam", "go over the old quizzes"]),
              ("the presentation order", ["have the intro go first", "start with the results"]),
              ("the study schedule", ["meet twice a week", "do one long session on Sundays"])],
    "neighbors": [("the block party date", ["hold it on a Saturday in June", "wait until school is out"]),
                  ("the street closure", ["ask the city to close the street", "keep it on the driveways"]),
                  ("the garden beds", ["build four raised beds", "start with two and add more later"]),
                  ("the group chat", ["move to an email list", "keep the group chat"]),
                  ("the music", ["hire a local band", "just use a speaker and a playlist"])],
    "book": [("next month's book", ["read the mystery", "read the memoir"]),
             ("the meeting spot", ["rotate homes", "use the library meeting room"]),
             ("the book length limit", ["keep picks under 300 pages", "allow longer books in the summer"]),
             ("the author visit", ["invite the author to a video call", "skip it this year"]),
             ("the meeting night", ["stay on Thursdays", "switch to the first Sunday of the month"])],
}
PERSONAL_IDEAS = {
    "team": ["send a short teaser email the week before", "ask a few customers for quotes", "record a two-minute walkthrough",
             "set up a feedback form", "do a dry run on Thursday", "make a one-page FAQ"],
    "project": ["make a shared checklist", "ask friends to help on the big day", "book everything by the end of the month",
                "keep all the receipts in one folder", "do a test run first", "split it into two weekends"],
    "volunteer": ["partner with the coffee shop for drop-offs", "post in the neighborhood app", "ask local businesses for donations",
                  "have a sign-up table at the farmers market", "make a short video for social media",
                  "give volunteers matching shirts"],
    "study": ["make a shared question bank", "do a mock exam on Sunday", "trade flashcards", "each explain one topic to the group",
              "book the study room early", "meet for thirty minutes every weekday"],
    "neighbors": ["put flyers in every mailbox", "start a sign-up sheet for food", "ask the city about free trash bags",
                  "set up a group email", "do a potluck instead of catering", "make name tags so people meet each other"],
    "book": ["pair each book with a movie night", "rotate who picks the book", "invite a local librarian",
             "keep a shared list of suggestions", "try one audiobook pick", "meet outdoors when it's warm"],
}
PERSONAL_CHECKINS = ["Busy week, but good.", "Pretty good. I finally took a day off.", "Tired, but excited about {focus}.",
                     "Good! I'm glad we're doing this today.", "Honestly a little stressed, but I'm here.",
                     "Not bad. My week was mostly errands.", "Great, actually. I got a lot done.",
                     "Okay. I'm still catching up from last week.", "Good. The weather helped."]
PERSONAL_STATUS = {
    "done": ["{task_cap} is done. I posted it in the group chat this morning.",
             "I finished {task}. Take a look when you can and tell me if anything's off.",
             "{task_cap} is finished, and it came out better than I expected."],
    "progress": ["{task_cap} is about {pct} percent done. I should have the rest by {day}.",
                 "I'm about halfway through {task}. No blockers so far.",
                 "I started {task}. It's taking longer than I thought, but it's moving."],
    "blocked": ["I'm stuck on {task}. I'm waiting to hear back from someone before I can finish it.",
                "{task_cap} is on hold until we decide a few things today."],
    "late": ["I didn't get to {task} yet, sorry. I'll have it by {day}.",
             "{task_cap} slipped this week. I can catch up by {day}."],
}
PERSONAL_SUMMARY = {"done": "{first} finished {task}", "progress": "{first} is working on {task}",
                    "blocked": "{first} is waiting on others for {task}", "late": "{first} will finish {task} by {day}"}
PERSONAL_DETAILS = ["It took most of my weekend, but it's worth it.", "I left a few notes in the doc for everyone.",
                    "If anyone has feedback, send it my way.", "I'll keep everyone posted in the chat.",
                    "I might need help with the last part.", "It should be easy from here."]
PERSONAL_ASKS = [("Is anything blocking you on {task}?", ["Mostly it's just time. I can finish it by {day}.",
                                                          "Not really, it's going fine.",
                                                          "I could use a second pair of eyes on it."]),
                 ("Do you need help with {task}?", ["Maybe on {day}, if someone's free for an hour.",
                                                    "I think I've got it, thanks.",
                                                    "Yes, could someone check my numbers?"]),
                 ("Can you send {task} to everyone after this?", ["Sure, I'll send it tonight.",
                                                                  "Yes, it's already in the shared folder."])]
PERSONAL_OPENS = ["Next, we need to decide on {choice}.", "Let's settle {choice} today.", "The big thing today is {choice}.",
                  "We keep putting off {choice}, so let's decide."]
PERSONAL_OPINIONS = ["I'd rather {option}. It's less work for everyone, and we can always change it later.",
                     "I vote we {option}. That's what worked last time, and nobody complained.",
                     "Honestly, I'm fine either way, but I lean toward the idea to {option}.",
                     "If we {option}, we'd probably save some money, which matters right now.",
                     "I like the idea to {option}, as long as we tell everyone by {day}.",
                     "I'm not sold on the idea to {other}. I think we should {option} instead."]
PERSONAL_QUESTIONS = [("What would it cost to {option}?", ["Probably around {money}, maybe less if we shop around.",
                                                           "Not much. Mostly our time."]),
                      ("How long would it take to {option}?", ["A couple of hours, if we split it up.",
                                                               "Maybe a full weekend, honestly."]),
                      ("Does anyone else need to sign off on {choice}?", ["No, it's our call.",
                                                                          "I'd run it by a couple of people first."]),
                      ("Have we done something like this before?", ["Once, a while back. It went fine.",
                                                                    "Not really, so it's a bit of an experiment."])]
PERSONAL_CONCERNS = ["My only worry is that not everyone can make it on a weekend.",
                     "My worry is that it ends up costing more than we think.", "What if the weather doesn't cooperate?",
                     "I'm worried we're taking on too much at once.", "We should make sure nobody ends up doing all the work."]
PERSONAL_RESPONSES = ["Fair point. We can plan a backup.", "That's true. Let's keep it small this time.",
                      "Good catch. I'll check on that before next time.", "We can split it up so it's not on one person."]
PERSONAL_AGREES = ["Okay, it sounds like we agree to {option}.", "Great, so we'll {option}.",
                   "Let's go with that and {option}. Everyone okay with that?"]
PERSONAL_DEFERS = ["We don't have enough info yet. Let's come back to {choice} next time.",
                   "Let's think about {choice} and decide on {day}."]
PERSONAL_IDEA_LINES = ["What if we {idea}?", "One idea: we could {idea}.", "Could we {idea}? I think people would like that."]
PERSONAL_IDEA_REPLIES = ["I like that.", "That could work, as long as someone owns it.", "Love it. I can help with that.",
                         "Maybe, but let's not take on too much."]
PERSONAL_TANGENTS = [("Did anyone watch the game last night?", "Don't spoil it, I haven't seen it yet."),
                     ("Is it just me, or is it freezing in here?", "No, the heater is acting up again."),
                     ("Sorry, my dog is barking.", "No worries, we can hear you fine."),
                     ("Has anyone tried the new coffee place downstairs?", "Yes, the cold brew is really good.")]
PERSONAL_CHATS = ["Here's the notes doc: https://example.com/notes", "Running five minutes late, start without me.",
                  "Can you share your screen?", "Sorry, my connection keeps dropping.", "+1 to that",
                  "I'll send the link after the call."]
PERSONAL_PLACES = ["Zoom", "Conference room B", "Hybrid: office and Zoom", "Library study room", "Community center"]


def cap(text):
    return text[:1].upper() + text[1:]


def fresh(s, pool, tag="", **extra):
    for template in s.rnd.sample(pool, len(pool)):
        mark = "p|%s|%s" % (tag, template)
        if mark not in s.used:
            s.used.add(mark)
            return template.format(**s.values(extra)).replace("..", ".")
    return ""


def fresh_pair(s, pool, tag="", **extra):
    for q, answers in s.rnd.sample(pool, len(pool)):
        mark = "p|%s|%s" % (tag, q)
        if mark not in s.used:
            s.used.add(mark)
            v = s.values(extra)
            return q.format(**v), s.rnd.choice(answers).format(**v)
    return None


class Plan:
    def __init__(self, rnd, kind, focus):
        self.kind, self.focus = kind, focus
        self.people = rnd.sample(PERSONAL_PEOPLE, rnd.randint(3, 6))
        self.choices = rnd.sample(PERSONAL_CHOICES[kind], len(PERSONAL_CHOICES[kind]))
        self.ideas = rnd.sample(PERSONAL_IDEAS[kind], len(PERSONAL_IDEAS[kind]))
        tasks = rnd.sample(PERSONAL_TASKS[kind], len(PERSONAL_TASKS[kind]))
        self.work = []
        for i, task in enumerate(tasks[:len(self.people) + 2]):
            status = rnd.choices(["done", "progress", "blocked", "late"], [4, 4, 1, 2])[0]
            self.work.append({"who": self.people[i % len(self.people)], "task": task, "status": status,
                              "pct": rnd.choice(range(30, 90, 10)), "day": rnd.choice(DAYS)})
        self.spare = tasks[len(self.work):]
        self.present = self.people[:]
        self.decisions, self.actions, self.checked = [], [], False


def p_checkin(s, plan, host):
    if plan.checked:
        return ""
    plan.checked = True
    s.say(host, "Let's go around quickly. How's everyone doing?")
    for who in plan.present:
        s.say(who, fresh(s, PERSONAL_CHECKINS, focus=plan.focus[1]))
    return "Everyone checked in."


def p_update(s, plan):
    item = next((w for w in plan.work if not w.get("said") and w["who"] in plan.present), None)
    if item is None:
        return ""
    item["said"] = True
    args = {"task": item["task"], "task_cap": cap(item["task"]), "pct": item["pct"], "day": item["day"]}
    text = s.rnd.choice(PERSONAL_STATUS[item["status"]]).format(**args)
    if s.rnd.random() < 0.5:
        text += " " + fresh(s, PERSONAL_DETAILS)
    s.say(item["who"], text.strip())
    if s.rnd.random() < 0.4:
        asked = fresh_pair(s, PERSONAL_ASKS, item["task"], **args)
        if asked:
            s.say(pick(s.rnd, plan.present, (item["who"],)), asked[0])
            s.say(item["who"], asked[1])
    return PERSONAL_SUMMARY[item["status"]].format(first=item["who"].split()[0], **args)


def p_action(s, plan, host):
    if not plan.spare:
        return ""
    task = plan.spare.pop(0)
    who = pick(s.rnd, plan.present)
    s.say(host, s.rnd.choice(["Who can take %s?", "Can someone own %s this week?", "Who wants to handle %s?"]) % task)
    s.say(who, s.rnd.choice(["I'll take it. I can have it done by %s." % s.rnd.choice(DAYS),
                             "I can do that. I'll post it in the chat when it's ready.",
                             "Sure, I'll handle it and report back next time."]))
    item = "%s will take %s." % (who.split()[0], task)
    plan.actions.append(item)
    return item


def p_idea(s, plan, host):
    if not plan.ideas:
        return ""
    idea = plan.ideas.pop(0)
    who = pick(s.rnd, plan.present)
    s.say(who, s.rnd.choice(PERSONAL_IDEA_LINES).format(idea=idea))
    reply = s.rnd.choice(PERSONAL_IDEA_REPLIES)
    s.say(pick(s.rnd, plan.present + [host], (who,)), reply)
    if reply.startswith("Maybe"):
        return "Discussed the idea to %s, but held off for now." % idea
    plan.actions.append("%s will %s." % (who.split()[0], idea))
    return "Agreed to %s; %s will lead it." % (idea, who.split()[0])


def p_decision(s, plan, host, until):
    if not plan.choices:
        return ""
    name, options = plan.choices.pop(0)
    s.say(host, fresh(s, PERSONAL_OPENS, name, choice=name) or "Next, %s." % name)
    goal = min(until, s.t + s.rnd.uniform(180, 600))
    turns = 0
    while s.t < goal and turns < 24:
        option = s.rnd.choice(options)
        other = next(o for o in options if o != option)
        roll = s.rnd.random()
        who = pick(s.rnd, plan.present)
        if roll < 0.5:
            text = fresh(s, PERSONAL_OPINIONS, name + option, option=option, other=other)
            if not text:
                break
            s.say(who, text)
        elif roll < 0.8:
            asked = fresh_pair(s, PERSONAL_QUESTIONS, name, option=option, choice=name)
            if not asked:
                continue
            s.say(who, asked[0])
            s.say(pick(s.rnd, plan.present + [host], (who,)), asked[1])
        else:
            worry = fresh(s, PERSONAL_CONCERNS, name)
            if not worry:
                continue
            s.say(who, worry)
            s.say(pick(s.rnd, plan.present + [host], (who,)), s.rnd.choice(PERSONAL_RESPONSES))
        turns += 1
    if s.rnd.random() < 0.12:
        a, b = s.rnd.choice(PERSONAL_TANGENTS)
        s.say(pick(s.rnd, plan.present), a)
        s.say(pick(s.rnd, plan.present), b)
        s.say(host, "Okay, back to %s." % name)
    title = cap(name)
    if s.rnd.random() < 0.85:
        final = s.rnd.choice(options)
        s.say(host, s.rnd.choice(PERSONAL_AGREES).format(option=final))
        s.say(pick(s.rnd, plan.present), s.rnd.choice(["Sounds good.", "Works for me.", "Yes, let's do it.", "Agreed."]))
        plan.decisions.append("%s: decided to %s." % (title, final))
        return "%s: decided to %s." % (title, final)
    s.say(host, s.rnd.choice(PERSONAL_DEFERS).format(choice=name, day=s.rnd.choice(DAYS)))
    return "%s: discussed; the decision moved to the next meeting." % title


def personal_build(rnd, kind, slots, start_minute, minutes, focus=""):
    found = next((f for f in PERSONAL_FOCUS[kind] if f[0] == focus), PERSONAL_FOCUS[kind][0])
    s = Script(rnd, start_minute)
    s.agenda = slots
    plan = Plan(rnd, kind, found)
    s.decisions, s.actions = plan.decisions, plan.actions
    host = SECRETARY
    people = plan.present
    late = people.pop() if len(people) > 3 and rnd.random() < 0.3 else ""
    target = minutes * 60
    weights = [5 if any(w in x.lower() for w in HEAVY + ("plan", "idea")) else 3 if any(w in x.lower() for w in SPOKEN + ("check",))
               else 1 for x in slots]
    order = s.clock()
    s.say(host, "Hi everyone, let's get started. It's %s" % order)
    s.say(host, "Most of today is about %s, but let's do a quick round first." % found[1])
    s.summary["__order"] = order
    if rnd.random() < 0.35:
        a, b = rnd.choice(GLITCHES)
        s.say(pick(rnd, people), a)
        s.say(host, b)
    for i, slot in enumerate(slots):
        key = slot.lower()
        left = max(0, target - s.t)
        until = s.t + left * weights[i] / (sum(weights[i:]) or 1)
        s.say(host, rnd.choice(["Next up, %s.", "Okay, %s.", "Let's move to %s.", "Next, %s."]) % slot)
        if "roll" in key or "attendance" in key or "quorum" in key:
            here = [host] + people
            s.say(host, "We have %s here today." % ", ".join(x.split()[0] for x in here))
            s.summary[slot] = "Present: %s." % ", ".join(here)
        elif "check" in key or "welcome" in key or "introduc" in key:
            s.summary[slot] = p_checkin(s, plan, host) or "Quick check-in."
        elif any(w in key for w in ("action", "next step", "owner", "assign")):
            s.summary[slot] = " ".join(run_blocks(s, [lambda u: p_action(s, plan, host)], until)[:4])
        elif "idea" in key or "brainstorm" in key:
            s.summary[slot] = " ".join(run_blocks(s, [lambda u: p_idea(s, plan, host)], until)[:4])
        elif "announce" in key or "next meeting" in key:
            day = rnd.choice(DAYS)
            s.say(host, "Next meeting is %s at the same time." % day)
            s.summary[slot] = "Next meeting is %s." % day
        elif any(w in key for w in SPOKEN):
            done = run_blocks(s, [lambda u: p_update(s, plan)], until, room=30)
            s.summary[slot] = cap("; ".join(done[:5])) + "." if done else ""
        else:
            s.summary[slot] = " ".join(run_blocks(s, [lambda u: p_decision(s, plan, host, u), lambda u: p_idea(s, plan, host)],
                                                  until)[:4])
        if late and rnd.random() < 0.5:
            s.say(late, "Sorry I'm late, traffic was bad.")
            s.say(host, "No problem, we just finished %s." % slot.lower())
            people.append(late)
            late = ""
    if s.t < target - 120:
        s.say(host, rnd.choice(["We still have some time. Anything else people want to bring up?",
                                "Before we wrap up, is there anything else?"]))
        extra = run_blocks(s, [lambda u: p_decision(s, plan, host, u), lambda u: p_idea(s, plan, host),
                               lambda u: p_update(s, plan), lambda u: p_action(s, plan, host)], target, room=60)
        s.summary["__other"] = " ".join(extra[:3])
    for i, (t, who, text) in enumerate(s.lines):
        if who == SECRETARY and rnd.random() < 0.2:
            s.lines[i] = (t, rnd.choice(MISHEARD), text)
    for _ in range(rnd.randint(1, 2 + minutes // 15)):
        text = s.line(PERSONAL_CHATS)
        if text:
            s.chat.append((round(rnd.uniform(30, max(60, s.t)), 1), pick(rnd, people), text))
    closing = s.clock()
    s.say(host, "Okay, that's everything. Thanks everyone, talk soon.")
    s.summary["__adjourn"] = closing
    return s


def personal_fills(s, slots):
    out = [{"under": slot, "text": s.summary[slot]} for slot in slots if s.summary.get(slot)]
    return {"order_time": s.summary.get("__order", ""), "adjourn_time": s.summary.get("__adjourn", ""), "fills": out,
            "summary": (s.decisions + s.actions)[:4]}


def fingerprint(rows):
    return hashlib.sha256("\n".join(row[2] for row in rows).encode("utf-8")).hexdigest()


KINDS = [("regular", "Regular Meeting"), ("regular", "General Meeting"), ("budget", "Budget Committee"),
         ("special", "Special Meeting"), ("workshop", "Planning Workshop"), ("election", "Appointments Meeting")]


def minutes_for(rnd, length, minutes):
    if minutes:
        return max(10, min(180, int(minutes * rnd.uniform(0.92, 1.08))))
    low, high = LENGTHS.get(length) or LENGTHS[rnd.choice(list(LENGTHS))]
    return rnd.randint(low, high)


def make(db, org, user, template, slots, count, seed=None, length="standard", minutes=None, personal=False):
    rnd = random.Random(seed if seed is not None else secrets.randbits(64))
    tz = ZoneInfo(TZ)
    today = dt.datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    old_rows = db.execute(select(models.Meeting.id, models.Meeting.title, models.Meeting.scheduled_at)
                          .where(models.Meeting.org_id == org.id, models.Meeting.sample.is_(True))).all()
    titles = {r.title for r in old_rows}
    days = {dt.datetime.fromtimestamp(r.scheduled_at, tz).date() for r in old_rows if r.scheduled_at}
    prints = set()
    for r in old_rows:
        texts = db.scalars(select(models.TranscriptLine.text).where(models.TranscriptLine.meeting_id == r.id)
                           .order_by(models.TranscriptLine.seq)).all()
        if texts:
            prints.add(hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest())
    kinds = (PERSONAL_KINDS if personal else KINDS)[:]
    rnd.shuffle(kinds)
    focus = [p[0] for p in rnd.sample(PROJECTS, len(PROJECTS)) if not any(p[0] in t for t in titles)] or [p[0] for p in PROJECTS]
    used = {k: [f[0] for f in rnd.sample(v, len(v)) if not any(f[0] in t for t in titles)] or [f[0] for f in v]
            for k, v in PERSONAL_FOCUS.items()} if personal else {}
    made, ended = [], 0
    for i in range(count):
        kind, label = kinds[i % len(kinds)]
        use = slots[:]
        if kind == "special":
            use = [x for x in slots if any(w in x.lower() for w in ("roll", "public", "new business", "consideration", "vote"))] or slots[:3]
        elif kind == "workshop":
            use = [x for x in slots if "approv" not in x.lower()] or slots
        stage = "scheduled" if i == 0 and count >= 4 else "open" if i == 1 and count >= 4 else "ended"
        start_minute = rnd.choice([0, 2, 3, 5, 7, 10, 15, 30, 45, 60])
        offset = rnd.randint(2, 12) if stage == "scheduled" else -(7 * (i + 1) + rnd.randint(0, 3))
        day = today + dt.timedelta(days=offset)
        while day.date() in days:
            day += dt.timedelta(days=1 if stage == "scheduled" else -1)
        days.add(day.date())
        when = day.replace(hour=14 + start_minute // 60, minute=start_minute % 60).timestamp()
        if stage == "open":
            when = time.time() - 20 * 60
        if personal:
            topic = used[kind].pop(0) if used[kind] else rnd.choice(PERSONAL_FOCUS[kind])[0]
        else:
            topic = focus[i % len(focus)]
        title = "Sample %s: %s" % (label, topic)
        n = 2
        while title in titles:
            title = "Sample %s: %s (%d)" % (label, topic, n)
            n += 1
        titles.add(title)
        length_min = minutes_for(rnd, length, minutes)
        mt = models.Meeting(org_id=org.id, title=title[:200], meeting_date=scheduling.label_for(when, TZ),
                            template_id=template.id, run_mode="live" if stage == "open" else "after", created_by=user.id,
                            draft={}, problems=[], snapshot_tail=[], scheduled_at=when, timezone=TZ, duration_min=length_min,
                            location=rnd.choice(PERSONAL_PLACES if personal else [
                                "Student Center 101", "Library 204", "Zoom", "College Center Board Room", "Science Building 120",
                                "Hybrid: Student Center 101 and Zoom"]),
                            status=stage, visibility="private", sample=True)
        db.add(mt)
        db.flush()
        if stage != "scheduled":
            for _ in range(6):
                s = (personal_build if personal else build)(rnd, kind, use, start_minute, length_min, topic)
                lines = s.lines if stage == "ended" else s.lines[: max(6, len(s.lines) // 2)]
                rows = [(t, who, text, "vtt") for t, who, text in lines] + [
                    (t, who, text, "chat") for t, who, text in s.chat if stage == "ended" and t <= s.t]
                rows.sort(key=lambda r: r[0])
                fp = fingerprint(rows)
                if fp not in prints:
                    prints.add(fp)
                    break
            for seq, (t, who, text, source) in enumerate(rows):
                db.add(models.TranscriptLine(meeting_id=mt.id, seq=seq, t=t, speaker=who, text=text, source=source))
            mt.duration_min = max(10, int(s.t // 60) + 1)
            if stage == "ended":
                ended += 1
                if ended % 2 == 1:
                    mt.draft = (personal_fills if personal else fills)(s, use)
                    mt.draft_rev = 1
                    mt.drafted_at = time.time()
        made.append(mt)
    return made
