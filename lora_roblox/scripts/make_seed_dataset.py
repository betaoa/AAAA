"""Gera dataset/seed.jsonl com exemplos originais (3D e VFX em Luau).

Estes exemplos servem para FIXAR O FORMATO. Um LoRA util precisa de centenas
a milhares de exemplos no mesmo formato (veja README.md).
"""
import json
import pathlib

SYSTEM = (
    "Voce e um assistente de Roblox Studio. Responda somente com codigo Luau "
    "valido, em um unico bloco, pronto para rodar em um Script do servidor."
)

EXAMPLES = [
    {
        "tags": ["3d"],
        "user": "Crie uma funcao que monta uma escada reta com N degraus em uma posicao dada.",
        "code": '''local function createStairs(parent: Instance, origin: Vector3, steps: number)
	local model = Instance.new("Model")
	model.Name = "Stairs"
	for i = 1, steps do
		local step = Instance.new("Part")
		step.Name = "Step" .. i
		step.Size = Vector3.new(6, 1, 2)
		step.Position = origin + Vector3.new(0, (i - 1) * 1, (i - 1) * 2)
		step.Anchored = true
		step.Material = Enum.Material.Concrete
		step.Parent = model
	end
	model.Parent = parent
	return model
end

createStairs(workspace, Vector3.new(0, 1, 0), 10)''',
    },
    {
        "tags": ["3d"],
        "user": "Monte uma arvore simples com tronco de madeira e copa redonda verde.",
        "code": '''local function createTree(parent: Instance, position: Vector3, height: number)
	local model = Instance.new("Model")
	model.Name = "Tree"

	local trunk = Instance.new("Part")
	trunk.Name = "Trunk"
	trunk.Size = Vector3.new(1.5, height, 1.5)
	trunk.Position = position + Vector3.new(0, height / 2, 0)
	trunk.Anchored = true
	trunk.Material = Enum.Material.Wood
	trunk.Color = Color3.fromRGB(98, 66, 40)
	trunk.Parent = model

	local leaves = Instance.new("Part")
	leaves.Name = "Leaves"
	leaves.Shape = Enum.PartType.Ball
	leaves.Size = Vector3.new(height, height, height)
	leaves.Position = position + Vector3.new(0, height + height / 4, 0)
	leaves.Anchored = true
	leaves.Material = Enum.Material.Grass
	leaves.Color = Color3.fromRGB(58, 125, 44)
	leaves.Parent = model

	model.PrimaryPart = trunk
	model.Parent = parent
	return model
end

createTree(workspace, Vector3.new(0, 0, 0), 8)''',
    },
    {
        "tags": ["3d", "vfx"],
        "user": "Crie uma tocha com uma Part de madeira e uma luz amarela que pisca de leve.",
        "code": '''local TweenService = game:GetService("TweenService")

local function createTorch(parent: Instance, position: Vector3)
	local torch = Instance.new("Part")
	torch.Name = "Torch"
	torch.Size = Vector3.new(0.6, 3, 0.6)
	torch.Position = position
	torch.Anchored = true
	torch.Material = Enum.Material.Wood
	torch.Color = Color3.fromRGB(90, 60, 35)
	torch.Parent = parent

	local light = Instance.new("PointLight")
	light.Color = Color3.fromRGB(255, 170, 60)
	light.Range = 16
	light.Brightness = 1.5
	light.Parent = torch

	local info = TweenInfo.new(0.6, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true)
	TweenService:Create(light, info, { Brightness = 2.5 }):Play()

	return torch
end

createTorch(workspace, Vector3.new(0, 2, 0))''',
    },
    {
        "tags": ["vfx"],
        "user": "Adicione um efeito de fogo em uma Part usando ParticleEmitter.",
        "code": '''local function addFire(part: BasePart)
	local emitter = Instance.new("ParticleEmitter")
	emitter.Name = "Fire"
	emitter.Texture = "rbxasset://textures/particles/fire_main.dds"
	emitter.Color = ColorSequence.new({
		ColorSequenceKeypoint.new(0, Color3.fromRGB(255, 200, 60)),
		ColorSequenceKeypoint.new(1, Color3.fromRGB(220, 40, 0)),
	})
	emitter.Size = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 1.5),
		NumberSequenceKeypoint.new(1, 0),
	})
	emitter.Transparency = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0.2),
		NumberSequenceKeypoint.new(1, 1),
	})
	emitter.Lifetime = NumberRange.new(0.6, 1.2)
	emitter.Rate = 40
	emitter.Speed = NumberRange.new(2, 4)
	emitter.SpreadAngle = Vector2.new(15, 15)
	emitter.Acceleration = Vector3.new(0, 4, 0)
	emitter.LightEmission = 1
	emitter.EmissionDirection = Enum.NormalId.Top
	emitter.Parent = part
	return emitter
end

addFire(workspace:WaitForChild("Torch"))''',
    },
    {
        "tags": ["vfx"],
        "user": "Crie uma funcao que solta uma explosao de faiscas em uma posicao quando algo for atingido.",
        "code": '''local Debris = game:GetService("Debris")

local function sparkBurst(position: Vector3, amount: number?)
	local anchor = Instance.new("Part")
	anchor.Name = "SparkAnchor"
	anchor.Size = Vector3.one
	anchor.Transparency = 1
	anchor.CanCollide = false
	anchor.CanQuery = false
	anchor.Anchored = true
	anchor.Position = position
	anchor.Parent = workspace

	local emitter = Instance.new("ParticleEmitter")
	emitter.Texture = "rbxasset://textures/particles/sparkles_main.dds"
	emitter.Color = ColorSequence.new(Color3.fromRGB(255, 220, 120))
	emitter.Size = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0.4),
		NumberSequenceKeypoint.new(1, 0),
	})
	emitter.Lifetime = NumberRange.new(0.3, 0.7)
	emitter.Speed = NumberRange.new(15, 30)
	emitter.SpreadAngle = Vector2.new(180, 180)
	emitter.Acceleration = Vector3.new(0, -40, 0)
	emitter.LightEmission = 1
	emitter.Rate = 0
	emitter.Enabled = false
	emitter.Parent = anchor

	emitter:Emit(amount or 20)
	Debris:AddItem(anchor, 1.5)
end

sparkBurst(Vector3.new(0, 5, 0), 30)''',
    },
    {
        "tags": ["vfx"],
        "user": "Faca uma Part brilhante se mover de um lado para o outro deixando um rastro (Trail).",
        "code": '''local TweenService = game:GetService("TweenService")

local orb = Instance.new("Part")
orb.Name = "Orb"
orb.Shape = Enum.PartType.Ball
orb.Size = Vector3.new(2, 2, 2)
orb.Material = Enum.Material.Neon
orb.Color = Color3.fromRGB(80, 200, 255)
orb.Anchored = true
orb.CanCollide = false
orb.Position = Vector3.new(-20, 6, 0)
orb.Parent = workspace

local a0 = Instance.new("Attachment")
a0.Position = Vector3.new(0, 0.8, 0)
a0.Parent = orb

local a1 = Instance.new("Attachment")
a1.Position = Vector3.new(0, -0.8, 0)
a1.Parent = orb

local trail = Instance.new("Trail")
trail.Attachment0 = a0
trail.Attachment1 = a1
trail.Lifetime = 0.8
trail.LightEmission = 1
trail.Color = ColorSequence.new(Color3.fromRGB(80, 200, 255), Color3.fromRGB(150, 80, 255))
trail.Transparency = NumberSequence.new({
	NumberSequenceKeypoint.new(0, 0),
	NumberSequenceKeypoint.new(1, 1),
})
trail.Parent = orb

local info = TweenInfo.new(2, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true)
TweenService:Create(orb, info, { Position = Vector3.new(20, 6, 0) }):Play()''',
    },
]


def main() -> None:
    out = pathlib.Path(__file__).resolve().parent.parent / "dataset" / "seed.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for ex in EXAMPLES:
            row = {
                "tags": ex["tags"],
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": ex["user"]},
                    {"role": "assistant", "content": "```lua\n" + ex["code"] + "\n```"},
                ],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(EXAMPLES)} exemplos -> {out}")


if __name__ == "__main__":
    main()
