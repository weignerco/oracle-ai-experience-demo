# Fraud Buster Challenge

> **Disclaimer:** This project is a proof-of-concept and demonstration prototype. It was never intended for production deployment and was built specifically to showcase the capabilities of Oracle Select AI in a rapid-development demo environment.

Can you beat AI at enterprise decision-making?
 This interactive application uses **Streamlit** and **Oracle Autonomous Database (ADB)** with **Select AI** to challenge users in identifying fraudulent transactions across various industries.

## Prerequisites

1.  **Oracle Autonomous Database:** An active instance is required. This project was developed and tested using the **Autonomous Database Dev Tier**.
    - *Note:* Compatibility with the "Always Free" tier has not been verified, particularly for "Select AI" resource requirements.
2.  **Cohere API Key:** Sign up at [Cohere](https://cohere.com/) to get an API key for the "Select AI" natural language features.
3.  **Python 3.9+:** To run the Streamlit application.

## Setup Instructions

### 1. Database Setup
1.  Log in to your Oracle Cloud Console and open **Database Actions (SQL)**.
2.  Run the contents of `database/schema.sql` to create the necessary tables.
3.  **Import Seed Data:**
    - Use the **Data Load** tool in Database Actions to upload `database/fraud_buster_sample_cases.csv` directly into the `CASES` table.
    - *Alternatively*, you can run the SQL inserts found in `database/seed_data.sql`.

### 2. AI Configuration
1.  Configure the **Select AI** profile and credentials by following the instructions and running the script in `database/select-ai-profile.sql`. This enables the natural language query features using the Cohere model.

### 3. Local Application Setup
1.  **Clone the repository.**
2.  **Create and Activate a Virtual Environment:**
    ```bash
    # Create the environment
    python3 -m venv venv

    # Activate it (macOS/Linux)
    source venv/bin/activate

    # For Windows:
    # .\venv\Scripts\activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r fraud-buster-app/requirements.txt
    ```
4.  **Download your ADB Wallet:**
    - Download the Client Credentials (Wallet) from your ADB console.
    - Unzip it into a folder named `adb_wallet` inside the `fraud-buster-app/` directory.
5.  **Configure Secrets:**
    - Copy `secrets.toml.example` to `fraud-buster-app/.streamlit/secrets.toml`.
    - Fill in your `DB_USER`, `DB_PASSWORD`, and `DB_DSN` (e.g., `yourdb_high`).
    - Set `WALLET_DIR = "adb_wallet"`.

## Running the App

Activate your virtual environment and start Streamlit:

```bash
# Activate venv (macOS/Linux)
source venv/bin/activate

# For Windows:
# .\venv\Scripts\activate

cd fraud-buster-app
streamlit run fraud_buster.py
```

## Project Structure
- `fraud-buster-app/`: Main application code and dependencies.
- `database/`: Database schema, seed data, and AI configuration scripts.
- `docs/`: Project documentation.
    - `context.md`: The original Product Requirement Document (PRD) and initial prompt used to design and build the application.
    - `architecture-diagram/`: Visual overview of the system design.
- `ui-design-mockup/`: Initial UI conceptual drafts and React mockups.
- `secrets.toml.example`: Template for local database configuration.
- `start.sh`: Helper script to activate venv and launch the app.

## Technical Design Decisions

### Why Cohere AI & Gemini CLI?
This project was designed as a rapid prototype with a focus on accessibility and cost-efficiency:
- **Free Trial Accessibility:** Cohere was chosen because of their generous trial API key program, allowing the "Select AI" features to be implemented and tested at zero cost.
- **Rapid Development with Gemini CLI:** The Gemini CLI was utilized to accelerate the build process. By using an AI-native development environment, I was able to iterate on the Streamlit UI and complex SQL logic in a fraction of the time.

### Security & Connectivity: Why Credentials over SQLcl MCP?
During the development phase, the primary goal was to reach a functional demo state as quickly as possible:
- **Speed of Implementation:** While a SQLcl MCP (Model Context Protocol) server offers a more advanced way for AI agents to interact with a database, setting it up requires more time and configuration.
- **Direct Access for Speed:** To minimize setup overhead, I provided Gemini CLI with direct database credentials. This allowed the agent to immediately begin building the schema and testing queries without additional infrastructure hurdles.
- **Credential Protection:** Although credentials were used for speed during the "build" phase, the repository is configured with a `.gitignore` and `secrets.toml.example` to ensure that no sensitive data or personal passwords are ever committed to source control.
