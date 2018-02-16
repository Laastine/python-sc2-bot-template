import json
from pathlib import Path

import sc2
from sc2.constants import *
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer

class MyBot(sc2.BotAI):
  with open(Path(__file__).parent / "../botinfo.json") as f:
    NAME = json.load(f)["name"]

  async def on_step(self, iteration):
    if iteration == 0:
      await self.chat_send(f"Name: {self.NAME}")

    cc = self.units(COMMANDCENTER)
    if not cc.exists:
      target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
      for unit in self.workers | self.units(MARINE):
        await self.do(unit.attack(target))
      return
    else:
      cc = cc.first

    for scv in self.units(SCV).idle:
      await self.do(scv.gather(self.state.mineral_field.closest_to(cc)))

    if self.can_afford(SCV) and self.workers.amount < 16 and cc.noqueue:
      await self.do(cc.train(SCV))

    elif self.supply_left < (2 if self.units(BARRACKS).amount < 3 else 4):
      if self.can_afford(SUPPLYDEPOT):
        await self.build(SUPPLYDEPOT, near=cc.position.towards(self.game_info.map_center, 3))

    elif self.units(BARRACKS).amount < 3 or (self.minerals > 400 and self.units(BARRACKS).amount < 4):
      if self.can_afford(BARRACKS):
        await self.build(BARRACKS, near=cc.position.towards(self.game_info.map_center, 7))

    for rax in self.units(BARRACKS).ready.noqueue:
      if not self.can_afford(MARINE):
        break
      await self.do(rax.train(MARINE))
