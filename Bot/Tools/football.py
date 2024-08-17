def context_for_goal_scorer():
    required_context = {
        "teams": ["Arsenal", "Chelsea", "Liverpool"],
        "competitions": ["Premier League", "FA Cup", "Champions League"]
    }
    optional_context = {
        "years": [str(year) for year in range(2010, 2024)]
    }
    return required_context, optional_context

def action_for_goal_scorer(context):
    if context['years'] == "default_value":
        context['years'] = "2024"
    return f"Top scorer data for {context['teams'][0]} in {context['competitions'][0]} {context['years']}"

def context_for_player_stats():
    required_context = {
        "players": ["Cristiano Ronaldo", "Lionel Messi", "Neymar Jr"]
    }
    optional_context = {}
    return required_context, optional_context

def action_for_player_stats(context):
    return f"here are the stats for {context["players"][0]}"
