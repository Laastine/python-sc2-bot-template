import json
from pathlib import Path
import random

import sc2
from sc2.constants import AbilityId, UnitTypeId
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer

from bot.attack import Attack

class MyBot(sc2.BotAI):

  def __init__(self):
    super()
    self.tech_lab_counter = 0
    self.weapons_started = False
    self.armor_started = False
    self.attack = Attack(self)

  with open(Path(__file__).parent / "../botinfo.json") as f:
    json = json.load(f)
    NAME = json["name"]
    flags = json["flags"]
    FLAGS = set(key for key,value in flags.items() if value == True)
    print(f'Flags: {FLAGS}')

  def has_flag(self, flag):
    return flag in self.FLAGS

  async def on_step(self, iteration):
    if iteration == 0:
      await self.chat_send(f"Name: {self.NAME}")

    cc = self.units(UnitTypeId.COMMANDCENTER)
    if not cc.exists:
      target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
      for unit in self.workers | self.units(UnitTypeId.MARINE):
        await self.do(unit.attack(target))
      return
    else:
      cc = cc.first

    # Run scouting subsystem
    await self.scvs(iteration, cc)
    await self.refinery()
    await self.build_units(iteration)

    await self.upgrade(iteration, cc)

    await self.engi_bay(cc)

    await self.medivacs(cc)

    await self.attack.on_step(iteration)

    await self.expand()


  def second_gas(self):
    return self.can_afford(UnitTypeId.REFINERY) and not self.already_pending(UnitTypeId.REFINERY) and self.units(UnitTypeId.REFINERY).ready.amount > 0 and self.units(UnitTypeId.REFINERY).ready.amount < 2 and self.attack.units_excluding_scout().amount > 30

  def second_command_center(self):
    return self.units(UnitTypeId.COMMANDCENTER).ready.amount > 1 and self.minerals > 400 and self.attack_units_excluding_scout().amount > 10

  async def upgrade(self, iteration, cc):
    # Barracks
    if (self.units(UnitTypeId.BARRACKS).amount < self.units(UnitTypeId.COMMANDCENTER).ready.amount * 2 and self.can_afford(UnitTypeId.BARRACKS)) or self.minerals > 1000 and self.units(UnitTypeId.BARRACKS).amount < 8:
      if self.can_afford(UnitTypeId.BARRACKS):
        await self.build(UnitTypeId.BARRACKS, near=cc.position.towards(self.game_info.map_center, 7))

    if self.units(UnitTypeId.BARRACKSTECHLAB).amount < 1 and self.units(UnitTypeId.BARRACKS).amount > 1 and not self.already_pending(UnitTypeId.BARRACKSTECHLAB):
      for barrack in self.units(UnitTypeId.BARRACKS).ready:
        if barrack.add_on_tag == 0 and not barrack.has_add_on and self.can_afford(UnitTypeId.BARRACKSTECHLAB):
          await self.do(barrack.build(UnitTypeId.BARRACKSTECHLAB))

    if self.units(UnitTypeId.BARRACKSTECHLAB).ready.exists:
      for lab in self.units(UnitTypeId.BARRACKSTECHLAB).ready:
        abilities = await self.get_available_abilities(lab)
        if AbilityId.RESEARCH_COMBATSHIELD in abilities and self.can_afford(AbilityId.RESEARCH_COMBATSHIELD):
          await self.do(lab(AbilityId.RESEARCH_COMBATSHIELD))
        if AbilityId.RESEARCH_CONCUSSIVESHELLS in abilities and self.can_afford(AbilityId.RESEARCH_CONCUSSIVESHELLS):
          await self.do(lab(AbilityId.RESEARCH_CONCUSSIVESHELLS))

  async def build_units(self, iteration):
    if self.minerals < 100:
      return

    build_rotation = [UnitTypeId.MARAUDER, UnitTypeId.MARINE]
    unit = build_rotation[random.randint(0,1) % len(build_rotation)]

    if iteration < 3600 and self.units(UnitTypeId.MARINE).amount > 15 and self.units(UnitTypeId.BARRACKSTECHLAB).amount == 0:
      return

    # Marine
    for rax in self.units(UnitTypeId.BARRACKS).ready.noqueue:
      if not self.can_afford(UnitTypeId.MARINE) or (self.can_afford(UnitTypeId.BARRACKSTECHLAB) and self.units(UnitTypeId.BARRACKSTECHLAB).amount == 0):
        break
      if self.units(UnitTypeId.BARRACKSTECHLAB).amount and self.can_afford(unit):
        await self.do(rax.train(unit))
      else:
        await self.do(rax.train(UnitTypeId.MARINE))

    for depot in self.units(UnitTypeId.SUPPLYDEPOT).ready:
      if not self.can_afford(AbilityId.MORPH_SUPPLYDEPOT_LOWER):
        break
      await self.do(depot(AbilityId.MORPH_SUPPLYDEPOT_LOWER))


  async def scvs(self, iteration, cc):
    # make scvs
    for cc in self.units(UnitTypeId.COMMANDCENTER).ready.noqueue:
      if self.can_afford(UnitTypeId.SCV) and self.units(UnitTypeId.SCV).amount < self.units(UnitTypeId.COMMANDCENTER).amount * 19:
        await self.do(cc.train(UnitTypeId.SCV))

    # gather closest mineral
    for scv in self.units(UnitTypeId.SCV).idle:
      await self.do(scv.gather(self.state.mineral_field.closest_to(scv)))

    # distribute
    await self.distribute_workers()

    # Do we have enough supply depots
    if self.supply_left < (10 if self.units(UnitTypeId.BARRACKS).amount < 2 else 20):
      if self.can_afford(UnitTypeId.SUPPLYDEPOT) and not self.already_pending(UnitTypeId.SUPPLYDEPOT):
        await self.build(UnitTypeId.SUPPLYDEPOT, near=cc.position.towards(self.game_info.map_center, 3))

  async def expand(self):
    if self.second_command_center():
      await self.expand_now()

  async def engi_bay(self, cc):
    if self.units(UnitTypeId.MARINE).amount > 6 and self.units(UnitTypeId.REFINERY).amount > 0 and self.units(UnitTypeId.ENGINEERINGBAY).amount < 1 and not self.already_pending(UnitTypeId.ENGINEERINGBAY) and self.can_afford(UnitTypeId.ENGINEERINGBAY):
      await self.build(UnitTypeId.ENGINEERINGBAY, near=cc.position.towards(self.game_info.map_center, 3))
    for bay in self.units(UnitTypeId.ENGINEERINGBAY).ready.noqueue:
      if not self.weapons_started and self.can_afford(AbilityId.ENGINEERINGBAYRESEARCH_TERRANINFANTRYWEAPONSLEVEL1):
        self.weapons_started = True
        await self.do(bay(AbilityId.ENGINEERINGBAYRESEARCH_TERRANINFANTRYWEAPONSLEVEL1))
    for bay in self.units(UnitTypeId.ENGINEERINGBAY).ready.noqueue:
      if not self.armor_started and self.can_afford(AbilityId.ENGINEERINGBAYRESEARCH_TERRANINFANTRYARMORLEVEL1):
        self.armor_started = True
        await self.do(bay(AbilityId.ENGINEERINGBAYRESEARCH_TERRANINFANTRYARMORLEVEL1))

  async def refinery(self):
    if self.can_afford(UnitTypeId.REFINERY) and not self.already_pending(UnitTypeId.REFINERY) and self.units(UnitTypeId.REFINERY).amount < 1:
      SCVs = self.workers.random
      target = self.state.vespene_geyser.closest_to(SCVs.position)
      await self.do(SCVs.build(UnitTypeId.REFINERY, target))
    elif self.second_gas():
      SCVs = self.workers.random
      target = self.state.vespene_geyser.closest_to(SCVs.position)
      await self.do(SCVs.build(UnitTypeId.REFINERY, target))

  async def medivacs(self, cc):
    if self.units(UnitTypeId.ENGINEERINGBAY).amount > 0 and self.can_afford(UnitTypeId.FACTORY) and self.units(UnitTypeId.FACTORY).amount < 1 and not self.already_pending(UnitTypeId.FACTORY):
      await self.build(UnitTypeId.FACTORY, near=cc.position.towards(self.game_info.map_center, 8))
    if self.units(UnitTypeId.FACTORY).ready.amount > 0 and self.can_afford(UnitTypeId.STARPORT) and self.units(UnitTypeId.STARPORT).amount < 1 and not self.already_pending(UnitTypeId.STARPORT):
      await self.build(UnitTypeId.STARPORT, near=cc.position.towards(self.game_info.map_center, 4))
    for starport in self.units(UnitTypeId.STARPORT).ready.noqueue:
      if not self.can_afford(UnitTypeId.MEDIVAC):
        break
      await self.do(starport.train(UnitTypeId.MEDIVAC))
