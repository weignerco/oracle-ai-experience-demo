-- ==========================================================
-- Fraud Buster Challenge - Select AI Profile Setup
-- Target: Oracle Autonomous Database
-- ==========================================================

-- 1. Create LLM Credential
----------------------------------------------------------
-- PREREQUISITE: You must have a Cohere API Key.
-- Run this as ADMIN or a user with DBMS_CLOUD privileges.

/*
BEGIN
  DBMS_CLOUD.CREATE_CREDENTIAL(
    credential_name => 'COHERE_CRED',
    credential_details => '{ "token": "YOUR_COHERE_API_KEY" }'
  );
END;
/
*/

-- 2. Create Select AI Profile
----------------------------------------------------------

BEGIN
  DBMS_CLOUD_AI.DROP_PROFILE(
    profile_name => 'FRAUD_BUSTER_AI',
    force        => TRUE
  );
EXCEPTION
  WHEN OTHERS THEN
    NULL;
END;
/

BEGIN
  DBMS_CLOUD_AI.CREATE_PROFILE(
    profile_name => 'FRAUD_BUSTER_AI',
    attributes   => '{
      "provider": "cohere",
      "credential_name": "COHERE_CRED",
      "object_list": [
        {"owner": "FRAUD_USER", "name": "CASES"},
        {"owner": "FRAUD_USER", "name": "PLAYERS"},
        {"owner": "FRAUD_USER", "name": "LEADERBOARD"},
        {"owner": "FRAUD_USER", "name": "PLAYER_CASE_RESULTS"}
      ],
      "enforce_object_list": true,
      "model": "command-nightly",
      "temperature": 0.2,
      "max_tokens": 300
    }',
    description  => 'Fraud Buster Select AI profile using Cohere'
  );
END;
/

-- 3. Optional: Cleanup
----------------------------------------------------------
-- TRUNCATE TABLE PLAYER_CASE_RESULTS;
-- TRUNCATE TABLE LEADERBOARD;
-- TRUNCATE TABLE PLAYERS;
