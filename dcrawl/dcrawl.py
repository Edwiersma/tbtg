import json
import sys

DEBUG = sys.platform != 'emscripten'

if DEBUG:
    from cmd_interface import CommandHandler
    from engine import GameInit
    try:
        with open('dcrawl.json') as json_file:
            GAME_DATA = json.load(json_file)
    except:
        with open('dcrawl/dcrawl.json') as json_file:
            GAME_DATA = json.load(json_file)


def get_game_data(search_set, key, value):
    return {k: v for k, v in GAME_DATA[search_set].items() if v.get(key) == value}


class GameInitIns(GameInit):
    def __init__(self):
        super().__init__()
        class_dict = get_game_data("object_definition", "object_class", "C_PlayerClass")
        race_dict = get_game_data("object_definition", "object_class", "C_PlayerRace")
        background_dict = get_game_data("object_definition", "object_class", "C_PlayerBackground")
        self.character_classes = (
            [c.get("class_weapon").lower() for c in class_dict.values()],
            " / ".join([f"<{c.get('color')}>{c.get('class_weapon')}</{c.get('color')}>" for c in class_dict.values()])
        )
        self.character_races = (
            [v.get("name").lower() for v in race_dict.values()],
            " / ".join([f"<o>{v}</o>" for v in race_dict.keys()])
        )
        self.character_backgrounds = (
            [v.get("name").lower() for v in background_dict.values()],
            " / ".join([f"<o>{v}</o>" for v in background_dict.keys()])
        )

    def fnc_set_player_class(self, cmd, arg):
        matched = [
            c for c in get_game_data("object_definition", "object_class", "C_PlayerClass").values()
            if cmd.lower() in c["class_weapon"].lower()
        ]
        class_instance = self._create_instance(obj_name=f"{arg}{matched[0].get('name').lower()}", struct=matched[0])
        self.player.player_class = class_instance

    def fnc_set_player_done(self, cmd, arg):
        self.fnc_set_player_stats(self.player)

    def fnc_set_player_stats(self, player=None):
        if not player:
            player = self.player
        for key in player.stats:
            player.stats[key] = (
                    player.base_stats[key] +
                    player.player_race.stats[key] +
                    player.player_class.stats[key] +
                    player.player_background.stats[key]
            )
        return player.stats

    def fnc_render_player(self):
        bstr = ["╔════╗", "{:^6}", "╠════╣", "║{:^+4}║", "╚({:>2})╝"]
        attrs = self.fnc_set_player_stats()
        player_ac = 12
        player_hp = 26
        player_lv = 3
        player_gold = 15

        lines = []
        name_box = []
        name_box.append("╔" + ("═" * 44) + "╗")
        name_box.append(f"║NAME: {self.player.name.upper():<13} CLASS: {self.player.player_class.name.upper():>16} ║")
        name_box.append(f"║RACE: {self.player.player_race.name.upper():<13} BACKGROUND: {self.player.player_background.name.upper():>11} ║")
        name_box.append(
            f"║AC: {player_ac:_^4} HP: {player_hp:_>4}/{player_hp:_<4} GOLD: ¤{player_gold:_^5} LVL: {player_lv:_^3}║")
        name_box.append("╚" + ("═" * 44) + "╝")
        lines += name_box

        attr_box = []
        attr_box.append("  ".join([bstr[1].format(s.upper()) for s in attrs.keys()]))
        attr_box.append("  ".join([bstr[0] for s in range(len(attrs.values()))]))
        attr_box.append("  ".join([bstr[3].format(int(round(s - 10) * 0.5)) for s in attrs.values()]))
        attr_box.append("  ".join([bstr[4].format(s) for s in attrs.values()]))

        lines += attr_box
        return("\n".join(lines))

handler = CommandHandler()
game_init = GameInitIns()
handler.engine_interface = game_init.handler_interface


def intro():
    first_question = next(iter(GAME_DATA["init"].values()))["steps"][0]["q"]
    return f"{game_init.run_intro()}\n\n{first_question}"


def send_cmd(cmd: str) -> str:
    print(f"### Input Sent: {cmd}")
    return handler.handle_command(cmd)


if DEBUG:
    print(intro())
    print(send_cmd("2"))
    print(send_cmd("Bob"))
    print(send_cmd("half-orc"))
    print(send_cmd("sword"))
    print(send_cmd("Soldier"))
    print(send_cmd("y"))
    print(send_cmd("Edwin"))
    print(send_cmd("halfling"))
    print(send_cmd("bow"))
    print(send_cmd("Criminal"))
    print(send_cmd("y"))
    print(send_cmd("2"))
    print(send_cmd("pm"))
