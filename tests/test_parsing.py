import nlsh


class TestIsCloudModel:
    def test_colon_cloud_suffix(self):
        assert nlsh.is_cloud_model("llama3.2:cloud") is True

    def test_dash_cloud_suffix(self):
        assert nlsh.is_cloud_model("llama3.2-cloud") is True

    def test_non_cloud_model(self):
        assert nlsh.is_cloud_model("llama3.2") is False


class TestStripCloudSuffix:
    def test_strips_colon_cloud(self):
        assert nlsh.strip_cloud_suffix("llama3.2:cloud") == "llama3.2"

    def test_strips_dash_cloud(self):
        assert nlsh.strip_cloud_suffix("llama3.2-cloud") == "llama3.2"

    def test_leaves_non_cloud_names_untouched(self):
        assert nlsh.strip_cloud_suffix("llama3.2") == "llama3.2"


class TestParseQaVerdicts:
    """parse_qa_verdicts keys each verdict by the command number on its line
    (1-based), not by the order the lines arrived in."""

    def test_parses_valid_lines(self):
        response = "1|PASS|Looks safe\n2|FAIL|Deletes data\n3|warn|Irreversible"
        assert nlsh.parse_qa_verdicts(response, 3) == {
            1: ("PASS", "Looks safe"),
            2: ("FAIL", "Deletes data"),
            3: ("WARN", "Irreversible"),
        }

    def test_verdict_is_keyed_by_its_command_number_not_line_order(self):
        # Regression: a skipped line used to shift command 3's FAIL onto
        # command 2 and leave command 3 with no verdict at all.
        response = "1|PASS|\n3|FAIL|wipes home"
        assert nlsh.parse_qa_verdicts(response, 3) == {
            1: ("PASS", ""),
            3: ("FAIL", "wipes home"),
        }

    def test_out_of_order_lines_are_assigned_to_their_own_commands(self):
        response = "2|FAIL|bad\n1|PASS|ok"
        assert nlsh.parse_qa_verdicts(response, 2) == {
            1: ("PASS", "ok"),
            2: ("FAIL", "bad"),
        }

    def test_ignores_numbers_beyond_the_number_of_commands(self):
        assert nlsh.parse_qa_verdicts("3|PASS|no such command", 2) == {}

    def test_ignores_out_of_range_numbers(self):
        assert nlsh.parse_qa_verdicts("7|PASS|out of range", 6) == {}
        assert nlsh.parse_qa_verdicts("0|PASS|out of range", 6) == {}

    def test_duplicate_numbers_keep_the_most_severe_verdict(self):
        response = "1|FAIL|dangerous\n1|PASS|fine"
        assert nlsh.parse_qa_verdicts(response, 1) == {1: ("FAIL", "dangerous")}
        response = "1|PASS|fine\n1|WARN|risky\n1|MISS|imprecise"
        assert nlsh.parse_qa_verdicts(response, 1) == {1: ("WARN", "risky")}

    def test_ignores_invalid_verdict_words(self):
        assert nlsh.parse_qa_verdicts("1|MAYBE|not a real verdict", 1) == {}

    def test_ignores_malformed_lines(self):
        assert nlsh.parse_qa_verdicts("not a verdict line at all", 1) == {}

    def test_reason_is_optional(self):
        assert nlsh.parse_qa_verdicts("1|PASS", 1) == {1: ("PASS", "")}

    def test_blank_input_returns_empty_dict(self):
        assert nlsh.parse_qa_verdicts("", 3) == {}


class TestAlignVerdicts:
    """align_verdicts turns the parsed mapping into one verdict per command,
    so no command can ever reach the execution gates without a verdict."""

    def test_returns_one_verdict_per_command_in_command_order(self):
        parsed = {2: ("FAIL", "bad"), 1: ("PASS", "ok")}
        assert nlsh.align_verdicts(parsed, 2) == [("PASS", "ok"), ("FAIL", "bad")]

    def test_command_without_a_verdict_is_treated_as_warn(self):
        aligned = nlsh.align_verdicts({1: ("PASS", "")}, 3)
        assert aligned[0] == ("PASS", "")
        assert aligned[1] == ("WARN", nlsh.NO_VERDICT_REASON)
        assert aligned[2] == ("WARN", nlsh.NO_VERDICT_REASON)

    def test_no_parsed_verdicts_means_every_command_is_warn(self):
        assert nlsh.align_verdicts({}, 2) == [("WARN", nlsh.NO_VERDICT_REASON)] * 2


class TestQaReview:
    def test_returns_aligned_verdicts_keyed_by_command_number(self, monkeypatch):
        class FakeClient:
            def chat(self, **kwargs):
                return "1|PASS|\n3|FAIL|wipes home"

        options = [("ls", ""), ("pwd", ""), ("rm -rf ~", "")]
        verdicts = nlsh.qa_review(FakeClient(), {"model": "m"}, "/bin/bash", "q", options)

        assert verdicts == [
            ("PASS", ""),
            ("WARN", nlsh.NO_VERDICT_REASON),
            ("FAIL", "wipes home"),
        ]


class TestParseCommandOptions:
    def test_parses_tagged_commands_and_explanations(self):
        response = "<c1>ls -la</c1><e1>List all files</e1><c2>pwd</c2><e2>Print directory</e2>"
        assert nlsh.parse_command_options(response) == [
            ("ls -la", "List all files"),
            ("pwd", "Print directory"),
        ]

    def test_missing_explanation_tag_defaults_to_empty_string(self):
        assert nlsh.parse_command_options("<c1>ls -la</c1>") == [("ls -la", "")]

    def test_filters_placeholder_commands(self):
        response = "<c1>command here</c1><e1>placeholder</e1>"
        assert nlsh.parse_command_options(response) == []

    def test_skips_indices_with_no_matching_tag(self):
        response = "<c2>pwd</c2><e2>Print directory</e2>"
        assert nlsh.parse_command_options(response) == [("pwd", "Print directory")]

    def test_no_tags_returns_empty_list(self):
        assert nlsh.parse_command_options("no tags here") == []


class TestExtractBaseCommand:
    def test_simple_command(self):
        assert nlsh.extract_base_command("ls -la") == "ls"

    def test_strips_leading_variable_assignment(self):
        assert nlsh.extract_base_command("LANG=C ls -la") == "ls"

    def test_stops_at_pipe(self):
        assert nlsh.extract_base_command("cat file.txt|grep foo") == "cat"

    def test_stops_at_redirect(self):
        assert nlsh.extract_base_command("echo hi>out.txt") == "echo"

    def test_empty_command_returns_empty_string(self):
        assert nlsh.extract_base_command("") == ""


class TestSanitizeForLog:
    def test_strips_newlines_and_carriage_returns(self):
        assert nlsh._sanitize_for_log("line1\nline2\r\nline3") == "line1 line2  line3"

    def test_plain_string_is_unchanged(self):
        assert nlsh._sanitize_for_log("plain text") == "plain text"
