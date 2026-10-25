//! JSON on stdout for results, JSON on stderr for errors. Nothing else is ever printed.

use std::io::Write;

use pecofence_ipc::IpcError;
use serde_json::{Map, Value};

/// A command's outcome: the JSON to print plus a secondary warning from the server and whether
/// part of a client-side batch failed (exit code 1 even though there is a result).
#[derive(Debug, Default)]
pub struct Reply {
    pub result: Value,
    pub warning: Option<String>,
    pub partial_failure: bool,
}

impl Reply {
    pub fn new(result: Value) -> Self {
        Self {
            result,
            warning: None,
            partial_failure: false,
        }
    }

    /// The payload as printed: `warning` merged into an object result, or wrapped beside it.
    pub fn payload(self) -> Value {
        match (self.result, self.warning) {
            (result, None) => result,
            (Value::Object(mut map), Some(warning)) => {
                map.insert("warning".into(), Value::String(warning));
                Value::Object(map)
            }
            (result, Some(warning)) => {
                serde_json::json!({ "result": result, "warning": warning })
            }
        }
    }
}

/// How results are printed: indentation, `--ascii` (`\uXXXX` for everything outside ASCII, so
/// a reader decoding stdout with a legacy code page still gets valid JSON) and `--fields`.
#[derive(Debug, Default, Clone)]
pub struct Style {
    pub pretty: bool,
    pub ascii: bool,
    /// Dotted paths kept by `--fields` (empty = everything).
    pub fields: Vec<String>,
}

impl Style {
    pub fn render(&self, value: &Value) -> String {
        let text = render(value, self.pretty);
        if self.ascii {
            escape_non_ascii(&text)
        } else {
            text
        }
    }

    /// The reply as printed: `--fields` applied to the result, the server's warning kept.
    pub fn shape(&self, reply: Reply) -> Value {
        Reply {
            result: project(reply.result, &self.fields),
            ..reply
        }
        .payload()
    }
}

pub fn render(value: &Value, pretty: bool) -> String {
    if pretty {
        serde_json::to_string_pretty(value)
    } else {
        serde_json::to_string(value)
    }
    .unwrap_or_else(|_| "null".into())
}

/// Pure: JSON text with every non-ASCII character written as `\uXXXX` (surrogate pairs above
/// U+FFFF). serde_json leaves them literal and they can only occur inside strings, so escaping
/// them there keeps the document equal.
pub fn escape_non_ascii(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut units = [0u16; 2];
    for c in text.chars() {
        if c.is_ascii() {
            out.push(c);
        } else {
            for u in c.encode_utf16(&mut units) {
                out.push_str(&format!("\\u{u:04x}"));
            }
        }
    }
    out
}

/// Pure: `--fields a,b.c` applied to a result. Arrays are projected element by element (so
/// `fence list --fields id,title` works like `rule list --fields list.name`); an object keeps
/// the named keys (sorted, like all output), nested paths as nested objects; an absent key
/// comes out as `null`. Keys match exactly, else case-insensitively. A top-level scalar is
/// returned as it is.
pub fn project(value: Value, fields: &[String]) -> Value {
    let paths: Vec<Vec<&str>> = fields
        .iter()
        .map(|f| f.trim())
        .filter(|f| !f.is_empty())
        .map(|f| f.split('.').filter(|s| !s.is_empty()).collect::<Vec<_>>())
        .filter(|p| !p.is_empty())
        .collect();
    if paths.is_empty() || !(value.is_array() || value.is_object()) {
        return value;
    }
    project_paths(value, &paths)
}

fn project_paths(value: Value, paths: &[Vec<&str>]) -> Value {
    match value {
        Value::Array(items) => Value::Array(
            items
                .into_iter()
                .map(|item| project_paths(item, paths))
                .collect(),
        ),
        Value::Object(mut map) => {
            let mut out = Map::new();
            for path in paths {
                let head = path[0];
                if out.contains_key(head) {
                    continue;
                }
                // Every requested path under this key, as tails; an empty tail = the whole value.
                let tails: Vec<Vec<&str>> = paths
                    .iter()
                    .filter(|p| p[0] == head)
                    .map(|p| p[1..].to_vec())
                    .collect();
                let key = if map.contains_key(head) {
                    Some(head.to_string())
                } else {
                    map.keys().find(|k| k.eq_ignore_ascii_case(head)).cloned()
                };
                let child = key.and_then(|k| map.remove(&k)).unwrap_or(Value::Null);
                let projected = if tails.iter().any(Vec::is_empty) {
                    child
                } else {
                    project_paths(child, &tails)
                };
                out.insert(head.to_string(), projected);
            }
            Value::Object(out)
        }
        // A path that goes on below a scalar or null names nothing.
        _ => Value::Null,
    }
}

pub fn print_result(reply: Reply, style: &Style) -> i32 {
    let exit = if reply.partial_failure { 1 } else { 0 };
    print_text(&style.render(&style.shape(reply)), true);
    exit
}

/// Writes to stdout without panicking when the reader went away (`| head`).
pub fn print_text(text: &str, newline: bool) {
    let mut out = std::io::stdout().lock();
    let _ = out.write_all(text.as_bytes());
    if newline {
        let _ = out.write_all(b"\n");
    }
    let _ = out.flush();
}

pub fn error_payload(error: &IpcError) -> Value {
    serde_json::json!({ "error": error })
}

pub fn print_error(error: &IpcError, style: &Style) -> i32 {
    let mut err = std::io::stderr().lock();
    let _ = writeln!(err, "{}", style.render(&error_payload(error)));
    let _ = err.flush();
    error.code.exit_code()
}

#[cfg(test)]
mod tests {
    use super::*;
    use pecofence_ipc::ErrorCode;
    use serde_json::json;

    #[test]
    fn warning_is_merged_into_objects_and_wrapped_otherwise() {
        let mut reply = Reply::new(json!({"changed": true}));
        reply.warning = Some("not saved".into());
        assert_eq!(
            reply.payload(),
            json!({"changed": true, "warning": "not saved"})
        );

        let mut reply = Reply::new(json!([1, 2]));
        reply.warning = Some("w".into());
        assert_eq!(reply.payload(), json!({"result": [1, 2], "warning": "w"}));

        assert_eq!(Reply::new(json!(5)).payload(), json!(5));
    }

    #[test]
    fn error_payload_has_the_documented_shape_and_exit_codes() {
        let e = IpcError::new(ErrorCode::NotRunning, "nope").hint("start it");
        let v = error_payload(&e);
        assert_eq!(v["error"]["code"], "not_running");
        assert_eq!(v["error"]["message"], "nope");
        assert_eq!(v["error"]["hint"], "start it");
        assert!(v["error"].get("details").is_none());
        assert_eq!(e.code.exit_code(), 3);
        assert_eq!(ErrorCode::Timeout.exit_code(), 4);
        assert_eq!(ErrorCode::Usage.exit_code(), 2);
        assert_eq!(ErrorCode::AmbiguousFence.exit_code(), 1);
        let compact = render(&v, false);
        assert!(!compact.contains('\n'));
        assert_eq!(serde_json::from_str::<Value>(&compact).unwrap(), v);
        assert!(render(&v, true).contains('\n'));
    }

    fn fields(list: &[&str]) -> Vec<String> {
        list.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn fields_project_lists_objects_and_nested_paths() {
        let fences = json!([
            {"id": "a", "title": "游戏", "rect": {"x": 1, "y": 2, "w": 3, "h": 4}, "tabs": []},
            {"id": "b", "title": "Work", "rect": null},
        ]);
        assert_eq!(
            project(fences.clone(), &fields(&["id", "rect.w", "missing"])),
            json!([
                {"id": "a", "rect": {"w": 3}, "missing": null},
                {"id": "b", "rect": null, "missing": null},
            ])
        );
        // A whole key wins over its sub-paths.
        let one = project(fences, &fields(&["title", "rect", "rect.x"]));
        assert_eq!(
            one[0],
            json!({"title": "游戏", "rect": {"x": 1, "y": 2, "w": 3, "h": 4}})
        );

        // Arrays inside objects are projected per element; keys match case-insensitively.
        let rules = json!({"keepUpdated": true, "list": [{"name": "PDFs", "index": 0}]});
        assert_eq!(
            project(rules, &fields(&["list.Name", "keepupdated"])),
            json!({"list": [{"Name": "PDFs"}], "keepupdated": true})
        );

        // No fields, blanks, or a scalar result: unchanged.
        assert_eq!(project(json!({"a": 1}), &[]), json!({"a": 1}));
        assert_eq!(
            project(json!({"a": 1}), &fields(&[" ", ""])),
            json!({"a": 1})
        );
        assert_eq!(project(json!(true), &fields(&["a"])), json!(true));
    }

    #[test]
    fn fields_keep_the_servers_warning() {
        let style = Style {
            fields: fields(&["moved"]),
            ..Style::default()
        };
        let mut reply = Reply::new(json!({"changed": true, "moved": 2, "to": "x"}));
        reply.warning = Some("1 item(s) stayed".into());
        assert_eq!(
            style.shape(reply),
            json!({"moved": 2, "warning": "1 item(s) stayed"})
        );
    }

    #[test]
    fn ascii_output_escapes_everything_outside_ascii_and_stays_equal() {
        let v = json!({"title": "游戏", "path": "C:\\Users\\me\\OneDrive\\デスクトップ", "emoji": "🎮"});
        let text = escape_non_ascii(&render(&v, false));
        assert!(text.is_ascii(), "{text}");
        assert!(text.contains(r"\u6e38\u620f"), "{text}");
        assert!(text.contains(r"\ud83c\udfae"), "{text}");
        assert_eq!(serde_json::from_str::<Value>(&text).unwrap(), v);
        let style = Style {
            ascii: true,
            pretty: true,
            ..Style::default()
        };
        assert_eq!(serde_json::from_str::<Value>(&style.render(&v)).unwrap(), v);
    }
}
