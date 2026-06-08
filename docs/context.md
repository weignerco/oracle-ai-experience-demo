# Fraud Buster Challenge (Can You Beat AI at Enterprise Decisions?)
There is an Oracle AI Experience event estimated at 100 attendees coming from different industries. i will be manning a demo booth. The goal is to setup a demo use case that would attract attendees. Something fun and engaging that would showcase oracle ai services.

## Landing Page
- Shows the title "Fraud Buster Challenge (Can You Beat AI at Enterprise Decisions?)"
- Shows a score tally "AI vs Humans" (must be visible on any page)
- Shows the Leaderboard (must be visible on any page)

## Player Flow
- Player clicks "Start Challenge"
- Enters Full Name and Company
- Choose an Industry (radio button): Banking/Finance, Insurance, Telco & Technology, Healthcare, Industrial, Government
- Player is presented with 3 Cases to solve and has 60 seconds to solve (timer visible)
- Scoring: no score if player did not select
- Once score is displayed, each case will have "Explain" button where AI generates the reason, signals, and other relevant information. Keep explanation brief.
- Record leaderboard and other scores in autonomous database

During gameplay:
- Player sees case
- Player chooses Legit/Fraud
- Scoring uses fixed IS_FRAUD value

After gameplay:
- SELECT AI explains each case
- SELECT AI summarizes player performance
- SELECT AI can answer leaderboard/event questions

Fallback:
- If SELECT AI fails, show CASES.EXPLANATION

## Cases Page
- 3 cases displayed side by side
- each case with brief explanation of scenario
- Player has two buttons "Legit" and "Fraud" for each case
- Confidence buttons: Confident, Not Sure

## Score Report Page
- Displays players total points
- same 3 cases displayed side by side
- "AI Explanation" button

## Scoring is based on three simple components:
1. Base Score (Accuracy)
- Correct answer: +100
- Wrong or no answer: 0

2. Speed Bonus
- < 10 seconds: +50
- 10–20 seconds: +30
- 20–30 seconds: +10
- 30+ seconds: 0

3. Confidence Bonus (optional)
- Correct + Confident: +30
- Wrong + Confident: –20
- Not sure: 0

---

Final score per case = Base + Speed Bonus + Confidence Bonus

Example:
Correct + fast (<10s) + confident → 100 + 50 + 30 = 180 points

Leaderboard ranks players by total score, with faster total time as a tie-breaker.

Leaderboard should also display the score tally for "AI vs Humans"

## Sample Cases
- Generate 30 random sample cases from identified industries and store in the autonomous database

## Industries
- Banking/Finance
- Insurance
- Telco & Technology
- Healthcare
- Industrial
- Government

## UX/UI
- refer to fraud-demo-react/react-ui-design-mockup.jsx
- AI chat window on the landing page where players can ask SELECT AI

Examples:
- Who is the top player today?
- Which company has the highest average score?
- Are humans beating AI overall?
- Which industry has the most fraud misses?
- Generate a summary of the game so far

## Stack
- Streamlit
- Connected Autonomous Database

## Autonomous Database
- use SELECT AI