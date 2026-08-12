from webwright.agents.default import DefaultAgent


class FakeModel:
    def format_message(self, *, role, content, extra=None):
        return {"role": role, "content": content, "extra": extra or {}}

    def format_observation_messages(self, message, outputs, template_vars):
        return []

    def get_template_vars(self):
        return {}


class FakeEnvironment:
    def execute(self, action):
        raise AssertionError("a no-action response must not execute the environment")

    def get_template_vars(self):
        return {}


def test_three_consecutive_no_action_responses_exit_as_stalled():
    agent = DefaultAgent(
        FakeModel(), FakeEnvironment(), system_template="system", instance_template="instance",
        debug_log=False, max_consecutive_no_action_steps=3,
    )
    message = {"role": "assistant", "content": "blocked", "extra": {
        "done": False, "actions": [],
    }}
    assert agent.execute_actions(message) == []
    assert agent.execute_actions(message) == []
    output = agent.execute_actions(message)
    assert output[-1]["role"] == "exit"
    assert output[-1]["extra"]["exit_status"] == "Stalled"


def test_real_action_resets_no_action_counter():
    class Environment(FakeEnvironment):
        def execute(self, action):
            return {"observation": {}}

    class Model(FakeModel):
        def format_observation_messages(self, message, outputs, template_vars):
            return []

        def get_template_vars(self):
            return {}

    agent = DefaultAgent(
        Model(), Environment(), system_template="system", instance_template="instance",
        debug_log=False, max_consecutive_no_action_steps=2,
    )
    empty = {"extra": {"done": False, "actions": []}}
    action = {"extra": {"done": False, "actions": [{"bash_command": "true"}]}}
    agent.execute_actions(empty)
    agent.execute_actions(action)
    assert agent.n_consecutive_no_action_steps == 0
    assert agent.execute_actions(empty) == []
