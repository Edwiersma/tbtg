import re
import sys
import json
import random

DEBUG = sys.platform != 'emscripten'
if DEBUG:
    try:
        with open('dcrawl.json') as json_file:
            GAME_DATA = json.load(json_file)
    except:
        with open('dcrawl/dcrawl.json') as json_file:
            GAME_DATA = json.load(json_file)

class GameObject:
    name: str = ""
    color: str = ""
    def __init__(self, name: str, **kwargs):
        self.name = name

    def render(self) -> str:
        return f"<{self.color}>{self.name}</{self.color}>"

    def __repr__(self) -> str:
        return f"{self.__class__} {self.render()}"

    def __str__(self) -> str:
        return self.render()

CLASS_REGISTRY: dict[str, type] = {"C_GameObject": GameObject}
OBJECT_REGISTRY: dict[str, object] = {}
_OBJ_TAG = re.compile(r"<o>([^<>]+)</o>")


class _FmtMap:
    """Mapping handed to str.format_map. Top-level keys resolve against the
    object's instance dict first; if missing, fall back to attribute lookup
    and — if the result is a no-arg callable — invoke it and embed the return.
    Lets format strings reference both variables (`{player}`) and method
    returns (`{fnc_render_player}`) uniformly."""
    __slots__ = ("_obj",)

    def __init__(self, obj):
        self._obj = obj

    def __getitem__(self, key):
        d = self._obj.__dict__
        if key in d:
            return d[key]
        attr = getattr(self._obj, key, None)
        if callable(attr):
            return attr()
        raise KeyError(key)

def create_class_object(dependencies):
    def make_init(all_defaults):
        def __init__(self, **kwargs):
            name = kwargs.pop("name", all_defaults.get("name", ""))
            GameObject.__init__(self, name)
            for k, v in all_defaults.items():
                if k != "name":
                    setattr(self, k, kwargs.get(k, v))
        return __init__

    created_classes = []
    for class_name in dependencies:
        class_def = GAME_DATA["object_classes"][class_name]
        parent_name = class_def.get("parent_class", "game_object")
        structure = {k: v for k, v in class_def.items() if k not in ("_attr", "parent_class")}
        parent_cls = CLASS_REGISTRY[parent_name]

        # Walk the parent MRO once now so __init__ doesn't have to on every instantiation.
        all_defaults = {}
        for parent in reversed(parent_cls.__mro__):
            for k, v in vars(parent).items():
                if not k.startswith("_") and not callable(v):
                    all_defaults[k] = v
        all_defaults.update(structure)

        cls = type(class_name, (parent_cls,), {**structure, "__init__": make_init(all_defaults)})
        CLASS_REGISTRY[class_name] = cls
        created_classes.append(cls)
    return created_classes


def resolve_class_dependency(resolve_class: str, dependencies=None):
    if dependencies is None:
        dependencies = list()
    if resolve_class in CLASS_REGISTRY:
        return CLASS_REGISTRY[resolve_class] if not dependencies else create_class_object(dependencies)[-1]
    class_def = GAME_DATA.get("object_classes", {}).get(resolve_class)
    if class_def is None:
        return None
    _parent = class_def.get("parent_class")
    if _parent:
        dependencies.insert(0, resolve_class)
        return resolve_class_dependency(_parent, dependencies)
    return None


def create_instance(class_name=None, obj_name=None, struct={}):
    cacheable = bool(obj_name) and not struct  # cache lookups without override
    if class_name:
        if class_name in CLASS_REGISTRY and not struct:
            return CLASS_REGISTRY[class_name]
        if class_name not in CLASS_REGISTRY:
            base = GAME_DATA["object_classes"].get(class_name)
            if base is None:
                return None
            struct = base | struct
    elif obj_name:
        if cacheable and obj_name in OBJECT_REGISTRY:
            return OBJECT_REGISTRY[obj_name]
        base = GAME_DATA["object_definition"].get(obj_name)
        if base is None:
            return None
        struct = base | struct
        class_name = struct.get("object_class")
        struct.pop("object_class")
    else:
        struct = None
    if struct:
        cls = resolve_class_dependency(class_name)
        if cls is None:
            return None
        inst = cls(**struct)
        if cacheable:
            OBJECT_REGISTRY[obj_name] = inst
        return inst
    else:
        return None

class GameInit:
    def __init__(self):
        self.player_count = 1
        self.players = []
        self.player = None
        self.initialized = list([(str(k), None, False) for k in GAME_DATA.get("init").keys()])
        self.init_step = 0
        self.override_commands = ["help", "reset", "credits"]
        self.current_player_num = 1
        self.game_data = {}
        self.response = ""

    def run_intro(self):
        return resolve_objects("\n".join(
            GAME_DATA.get("game_intro")
        ))

    def handler_interface(self, cmd: str | None) -> str:
        if isinstance(cmd, str) and cmd.strip().lower() == "exit":
            return "__EXIT__"
        for i, (init_name, init_set, initialized) in enumerate(self.initialized):
            if not initialized:
                initialize = self.initialize(i, init_name, init_set, cmd)
                return resolve_objects(initialize)

        #Finalize Init
        self.game_data["players"] = self.players
        init_summary = []
        for k, v in self.game_data.items():
            init_summary.append(f"{k}: {v}")
        for p in self.players:
            init_summary.append(str(p.__dict__))
        return "\n".join(init_summary)

    def _create_instance(self, class_name=None, obj_name=None, struct={}):
        return create_instance(class_name=class_name, obj_name=obj_name, struct=struct)

    def initialize(self, i, init_name, init_set, cmd=None):
        if not init_set: init_set = init_name
        steps = GAME_DATA.get("init").get(init_set).get("steps")
        step = steps[self.init_step]
        if cmd is None:
            return self._resolve_return(step.get("q").format_map(_FmtMap(self)))

        if (r := self._resolve_response(step.get("r", None), cmd)) is not None: return r
        if (r := self._resolve_answer(step.get("a", None), step, cmd)) is not None: return r
        if (r := self._resolve_game_var(step.get("game_var", None), cmd)) is not None: return r
        if (r := self._resolve_game_fnc(step.get("game_fnc", None), cmd)) is not None: return r

        self.init_step += 1
        if self.init_step >= len(steps):
            self.initialized[i] = (init_name, init_set, True)
            self.init_step = 0
            return self.handler_interface(None)

        return self._resolve_return(steps[self.init_step].get("q").format_map(_FmtMap(self)))

    def _resolve_response(self, response_list, cmd):
        if response_list:
            cmd_response = response_list.get(cmd) or response_list.get("_", "")
            if cmd_response:
                cmd_response = f"{random.choice(cmd_response)}\n" if isinstance(cmd_response, list) else f"{cmd_response}\n"
            self.response = cmd_response

    def _resolve_answer(self, a_required, step, cmd):
        if a_required:
            cmd = cmd.lower()
            if isinstance(a_required, str):
                a_required = a_required.format_map(_FmtMap(self))
                if f"'{cmd}'" not in a_required:
                    return self._resolve_return(step.get("q").format_map(_FmtMap(self)))
            elif isinstance(a_required, list):
                if cmd not in a_required:
                    return self._resolve_return(step.get("q").format_map(_FmtMap(self)))

    def _resolve_game_fnc(self, game_fnc, cmd):
        if game_fnc:
            _fnc_resolved = getattr(self, game_fnc[0])
            result = _fnc_resolved(cmd, game_fnc[1])
            if result == "reset_all":
                pass
            elif result == "reset_set":
                self.init_step = 0
                return self.handler_interface(None)
            elif result == "reset_step":
                return self.handler_interface(None)

    def _resolve_game_var(self, game_var, cmd):
        if game_var:
            prefix = game_var[1] if len(game_var) > 1 else ""
            inst_obj = create_instance(obj_name=f"{prefix}{cmd.lower()}")
            if inst_obj:
                cmd = inst_obj
            if "." in game_var[0]:
                obj_name, attr = game_var[0].split(".", 1)
                setattr(getattr(self, obj_name), attr, cmd)
            else:
                self.game_data[game_var[0]] = cmd

    def _resolve_return(self, text):
        while True:
            resolved = text.format_map(_FmtMap(self))
            if resolved == text:
                break
            text = resolved
        response, self.response = self.response, ""
        return response + resolved

    def fnc_set_player_count(self, cmd, arg):
        self.player_count = int(cmd)
        for i in range(self.player_count):
            self.initialized.insert(i + 2, (f"player_init_{i}", "player_init", False))
        self.initialized.pop(1)

    def fnc_new_player(self, cmd, arg):
        self.player = create_instance(class_name="C_Player", struct={"name": cmd})
        self.players.append(self.player)
        self.current_player_num += 1

    def _fnc_set_player_done(self, cmd, arg):
        if cmd == "y":
            self.fnc_set_player_done(cmd, arg)
        else:
            if self.player in self.players:
                self.players.remove(self.player)
            self.current_player_num -= 1
            return "reset_set"

    def fnc_set_player_done(self):
        pass


def resolve_objects(text: str) -> str:
    def _repl(m):
        key = m.group(1)
        obj = create_instance(obj_name=key)
        return obj.render() if obj is not None else f"<dim>{key}</dim>"
    return _OBJ_TAG.sub(_repl, text)
