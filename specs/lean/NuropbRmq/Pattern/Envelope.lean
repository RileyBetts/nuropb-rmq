/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.Bytes

/-!
JSON-RPC 2.0 envelope (spec-pure body). Compact encoding matches Python
`separators=(",", ":")` for objects/strings used on the mesh.
-/

namespace NuropbRmq.Pattern.Envelope

open NuropbRmq.Protocol.Bytes

inductive Json where
  | null
  | bool (b : Bool)
  | num (n : Int)
  | str (s : String)
  | arr (xs : List Json)
  | obj (kvs : List (String × Json))
  deriving Repr, Inhabited

def escape (s : String) : String :=
  Id.run do
    let mut out := ""
    for c in s.toList do
      if c == '"' then out := out ++ "\\\""
      else if c == '\\' then out := out ++ "\\\\"
      else if c == '\n' then out := out ++ "\\n"
      else out := out.push c
    pure out

partial def encodeJson : Json → String
  | .null => "null"
  | .bool true => "true"
  | .bool false => "false"
  | .num n => toString n
  | .str s => "\"" ++ escape s ++ "\""
  | .arr xs => "[" ++ String.intercalate "," (xs.map encodeJson) ++ "]"
  | .obj kvs =>
    let parts := kvs.map (fun (k, v) => "\"" ++ escape k ++ "\":" ++ encodeJson v)
    "{" ++ String.intercalate "," parts ++ "}"

def skipWs : List Char → List Char
  | ' ' :: rest | '\n' :: rest | '\t' :: rest | '\r' :: rest => skipWs rest
  | cs => cs

partial def parseString : List Char → Option (String × List Char)
  | '"' :: rest =>
    let rec go (cs : List Char) (acc : String) : Option (String × List Char) :=
      match cs with
      | [] => none
      | '"' :: rest => some (acc, rest)
      | '\\' :: d :: rest => go rest (acc.push d)
      | c :: rest => go rest (acc.push c)
    go rest ""
  | _ => none

def startsWith (cs : List Char) (tok : List Char) : Option (List Char) :=
  match tok, cs with
  | [], rest => some rest
  | t :: ts, c :: cs => if t == c then startsWith cs ts else none
  | _, _ => none

partial def parseJson (cs0 : List Char) : Option (Json × List Char) :=
  match skipWs cs0 with
  | [] => none
  | cs =>
    if let some rest := startsWith cs ['n', 'u', 'l', 'l'] then some (.null, rest)
    else if let some rest := startsWith cs ['t', 'r', 'u', 'e'] then some (.bool true, rest)
    else if let some rest := startsWith cs ['f', 'a', 'l', 's', 'e'] then some (.bool false, rest)
    else if cs.head? == some '"' then
      match parseString cs with
      | some (str, rest) => some (.str str, rest)
      | none => none
    else if cs.head?.any (fun c => c == '-' || c.isDigit) then
      let rec digits (xs : List Char) (acc : String) : String × List Char :=
        match xs with
        | c :: rest => if c.isDigit then digits rest (acc.push c) else (acc, xs)
        | [] => (acc, [])
      let (raw, rest) :=
        match cs with
        | '-' :: rest =>
          let (d, r) := digits rest "-"
          (d, r)
        | _ => digits cs ""
      match raw.toInt? with
      | some n => some (.num n, rest)
      | none => none
    else if cs.head? == some '[' then
      let rec items (xs : List Char) (acc : List Json) : Option (List Json × List Char) :=
        match skipWs xs with
        | ']' :: rest => some (acc, rest)
        | xs =>
          match parseJson xs with
          | none => none
          | some (v, xs) =>
            match skipWs xs with
            | ',' :: rest => items rest (acc ++ [v])
            | ']' :: rest => some (acc ++ [v], rest)
            | _ => none
      match cs with
      | _ :: rest =>
        match items rest [] with
        | some (vs, rest) => some (.arr vs, rest)
        | none => none
      | [] => none
    else if cs.head? == some '{' then
      let rec kvs (xs : List Char) (acc : List (String × Json)) :
          Option (List (String × Json) × List Char) :=
        match skipWs xs with
        | '}' :: rest => some (acc, rest)
        | xs =>
          match parseString (skipWs xs) with
          | none => none
          | some (k, xs) =>
            match skipWs xs with
            | ':' :: rest =>
              match parseJson rest with
              | none => none
              | some (v, xs) =>
                match skipWs xs with
                | ',' :: rest => kvs rest (acc ++ [(k, v)])
                | '}' :: rest => some (acc ++ [(k, v)], rest)
                | _ => none
            | _ => none
      match cs with
      | _ :: rest =>
        match kvs rest [] with
        | some (pairs, rest) => some (.obj pairs, rest)
        | none => none
      | [] => none
    else none

def parse (s : String) : Option Json :=
  match parseJson s.toList with
  | some (j, _) => some j
  | none => none

def objGet (j : Json) (k : String) : Option Json :=
  match j with
  | .obj kvs => (kvs.find? (fun p => p.1 == k)).map (·.2)
  | _ => none

def asStr : Json → Option String
  | .str s => some s
  | _ => none

def encodeRequest (method : String) (params : Json) (requestId : String) : ByteArray :=
  utf8 (encodeJson (.obj [
    ("jsonrpc", .str "2.0"),
    ("method", .str method),
    ("params", params),
    ("id", .str requestId),
  ]))

def encodeResult (result : Json) (requestId : String) : ByteArray :=
  utf8 (encodeJson (.obj [
    ("jsonrpc", .str "2.0"),
    ("result", result),
    ("id", .str requestId),
  ]))

def encodeError (code : Int) (message : String) (requestId : Option String) (data : Json) : ByteArray :=
  let errObj := .obj [("code", .num code), ("message", .str message), ("data", data)]
  let idVal : Json := match requestId with | some id => .str id | none => .null
  utf8 (encodeJson (.obj [
    ("jsonrpc", .str "2.0"),
    ("error", errObj),
    ("id", idVal),
  ]))

def encodeNotification (method : String) (params : Option Json) : ByteArray :=
  let kvs := [("jsonrpc", Json.str "2.0"), ("method", .str method)]
  let kvs := match params with | some p => kvs ++ [("params", p)] | none => kvs
  utf8 (encodeJson (.obj kvs))

inductive DecodeErr where
  | invalidEnvelope
  deriving Repr

def decodeMessage (body : ByteArray) : Except DecodeErr Json :=
  match fromUtf8 body with
  | none => .error .invalidEnvelope
  | some s =>
    match parse s with
    | none => .error .invalidEnvelope
    | some j =>
      match objGet j "jsonrpc" with
      | some (.str "2.0") => .ok j
      | _ => .error .invalidEnvelope

def decodeRequest (body : ByteArray) : Except DecodeErr (String × Json × String) :=
  match decodeMessage body with
  | .error e => .error e
  | .ok j =>
    match objGet j "method" >>= asStr, objGet j "id" >>= asStr with
    | some method, some id => .ok (method, (objGet j "params").getD .null, id)
    | _, _ => .error .invalidEnvelope

def decodeNotification (body : ByteArray) : Except DecodeErr (String × Json) :=
  match decodeMessage body with
  | .error e => .error e
  | .ok j =>
    if (objGet j "result").isSome || (objGet j "error").isSome then .error .invalidEnvelope
    else if (objGet j "id").isSome then .error .invalidEnvelope
    else
      match objGet j "method" >>= asStr with
      | some method => .ok (method, (objGet j "params").getD .null)
      | none => .error .invalidEnvelope

inductive RpcResult where
  | ok (value : Json)
  | err (code : Int) (message : String) (data : Json)
  deriving Repr

def decodeResponse (body : ByteArray) : Except DecodeErr RpcResult :=
  match decodeMessage body with
  | .error e => .error e
  | .ok j =>
    if let some r := objGet j "result" then .ok (.ok r)
    else if let some e := objGet j "error" then
      let code := match objGet e "code" with | some (.num n) => n | _ => -32000
      let msg := match objGet e "message" >>= asStr with | some s => s | none => "error"
      let data := (objGet e "data").getD .null
      .ok (.err code msg data)
    else .error .invalidEnvelope

end NuropbRmq.Pattern.Envelope
