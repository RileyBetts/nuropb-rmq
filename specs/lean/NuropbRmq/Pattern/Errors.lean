/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
JSON-RPC error taxonomy (Python `patterns.errors`).
-/

namespace NuropbRmq.Pattern.Errors

def INVALID_ID : Int := -33001
def ID_COLLISION : Int := -33002
def INVALID_ENVELOPE : Int := -33003
def UNAUTHORIZED : Int := -33100
def CLAIMS_MISSING : Int := -33101
def CLAIMS_EXPIRED : Int := -33102
def CLAIMS_UNBOUND : Int := -33103
def BIND_REFUSED : Int := -33201
def REQUEST_TIMEOUT : Int := -33300
def CONNECTION_LOST : Int := -33400
def CONNECTION_BLOCKED : Int := -33401
def PUBLISH_NACK : Int := -33402
def PUBLISH_RETURNED : Int := -33403
def SERVER_ERROR : Int := -32000

def codeName (code : Int) : String :=
  if code == INVALID_ID then "INVALID_ID"
  else if code == ID_COLLISION then "ID_COLLISION"
  else if code == INVALID_ENVELOPE then "INVALID_ENVELOPE"
  else if code == UNAUTHORIZED then "UNAUTHORIZED"
  else if code == CLAIMS_MISSING then "CLAIMS_MISSING"
  else if code == CLAIMS_EXPIRED then "CLAIMS_EXPIRED"
  else if code == CLAIMS_UNBOUND then "CLAIMS_UNBOUND"
  else if code == BIND_REFUSED then "BIND_REFUSED"
  else if code == REQUEST_TIMEOUT then "REQUEST_TIMEOUT"
  else if code == CONNECTION_LOST then "CONNECTION_LOST"
  else if code == CONNECTION_BLOCKED then "CONNECTION_BLOCKED"
  else if code == PUBLISH_NACK then "PUBLISH_NACK"
  else if code == PUBLISH_RETURNED then "PUBLISH_RETURNED"
  else if code == SERVER_ERROR then "SERVER_ERROR"
  else "UNKNOWN"

end NuropbRmq.Pattern.Errors
