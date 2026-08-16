"""
Ready-made server templates used by the /setup command.

Each template describes everything needed to turn an empty Discord server
into a fully organized one: roles, categories, and the text/voice channels
inside each category. Channel names use emoji prefixes so the server looks
polished immediately after setup, with no manual cleanup needed.

Structure of a template:
{
    "label": short name shown in the picker,
    "emoji": emoji shown next to it,
    "description": one-line description shown in the picker,
    "color": discord.Color used for the confirmation embed,
    "roles": [
        {"name": str, "color": discord.Color, "hoist": bool, "mentionable": bool},
        ...
    ],
    "categories": [
        {
            "name": "📋 CATEGORY NAME",
            "channels": [
                {"name": "📢・channel-name", "type": "text" | "voice" | "forum" | "stage", "topic": optional str},
                ...
            ],
        },
        ...
    ],
}
"""

import discord

TEMPLATES = {
    "gaming": {
        "label": "Gaming",
        "emoji": "🎮",
        "description": "A lively hub for a gaming community with LFG and clip channels",
        "color": discord.Color.blurple(),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "🔧 Moderator", "color": discord.Color.orange(), "hoist": True, "mentionable": True},
            {"name": "🎮 Gamer", "color": discord.Color.blurple(), "hoist": True, "mentionable": False},
            {"name": "🌱 Newbie", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text", "topic": "Official server announcements"},
                    {"name": "📜・rules", "type": "text", "topic": "Server rules — read before chatting"},
                    {"name": "🎉・events", "type": "text", "topic": "Upcoming community events and tournaments"},
                ],
            },
            {
                "name": "💬 COMMUNITY",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "🤖・bot-commands", "type": "text"},
                    {"name": "📸・media-share", "type": "text"},
                    {"name": "😂・memes", "type": "text"},
                ],
            },
            {
                "name": "🎮 GAMING",
                "channels": [
                    {"name": "🎯・looking-for-group", "type": "text", "topic": "Find teammates to play with"},
                    {"name": "🏆・clips-and-highlights", "type": "text"},
                    {"name": "🛠️・game-suggestions", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・General Voice", "type": "voice"},
                    {"name": "🎮・Gaming Room 1", "type": "voice"},
                    {"name": "🎮・Gaming Room 2", "type": "voice"},
                    {"name": "🎵・Music Lounge", "type": "voice"},
                    {"name": "🔇・AFK", "type": "voice"},
                ],
            },
        ],
    },
    "community": {
        "label": "Community",
        "emoji": "🌐",
        "description": "A general-purpose social server for any kind of community",
        "color": discord.Color.green(),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "🔧 Moderator", "color": discord.Color.orange(), "hoist": True, "mentionable": True},
            {"name": "🌟 VIP", "color": discord.Color.gold(), "hoist": True, "mentionable": False},
            {"name": "👤 Member", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 WELCOME",
                "channels": [
                    {"name": "📢・announcements", "type": "text", "topic": "Official server announcements"},
                    {"name": "📜・rules", "type": "text", "topic": "Server rules — read before chatting"},
                    {"name": "👋・introductions", "type": "text", "topic": "Introduce yourself to the community"},
                ],
            },
            {
                "name": "💬 GENERAL",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "🎉・off-topic", "type": "text"},
                    {"name": "😂・memes", "type": "text"},
                    {"name": "📸・selfies-and-media", "type": "text"},
                ],
            },
            {
                "name": "🎨 CREATIVE",
                "channels": [
                    {"name": "🎨・showcase", "type": "text", "topic": "Show off what you're working on"},
                    {"name": "💡・suggestions", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・Lounge", "type": "voice"},
                    {"name": "🎵・Music", "type": "voice"},
                    {"name": "🎮・Gaming Voice", "type": "voice"},
                ],
            },
        ],
    },
    "education": {
        "label": "Study & Education",
        "emoji": "📚",
        "description": "A focused space for study groups, tutoring, and classes",
        "color": discord.Color.teal(),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "🎓 Tutor", "color": discord.Color.teal(), "hoist": True, "mentionable": True},
            {"name": "📘 Student", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text"},
                    {"name": "📜・rules", "type": "text"},
                    {"name": "❓・faq", "type": "text"},
                ],
            },
            {
                "name": "📚 STUDY",
                "channels": [
                    {"name": "📖・general-study", "type": "text"},
                    {"name": "✏️・homework-help", "type": "text"},
                    {"name": "🧠・resources", "type": "text"},
                    {"name": "💡・study-tips", "type": "text"},
                ],
            },
            {
                "name": "🗣️ DISCUSSION",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "🎯・subject-specific", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・Study Room 1", "type": "voice"},
                    {"name": "🔊・Study Room 2", "type": "voice"},
                    {"name": "🤫・Silent Study", "type": "voice"},
                    {"name": "🎵・Break Room", "type": "voice"},
                ],
            },
        ],
    },
    "creator": {
        "label": "Content Creator",
        "emoji": "🎥",
        "description": "A hub for a streamer/YouTuber and their subscriber community",
        "color": discord.Color.magenta(),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "🎬 Creator", "color": discord.Color.magenta(), "hoist": True, "mentionable": True},
            {"name": "⭐ Subscriber", "color": discord.Color.gold(), "hoist": True, "mentionable": False},
            {"name": "👤 Member", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text"},
                    {"name": "📜・rules", "type": "text"},
                    {"name": "🔗・socials-and-links", "type": "text", "topic": "All official links in one place"},
                ],
            },
            {
                "name": "🎥 CONTENT",
                "channels": [
                    {"name": "🎬・latest-uploads", "type": "text"},
                    {"name": "💡・content-ideas", "type": "text"},
                    {"name": "📈・feedback", "type": "text"},
                ],
            },
            {
                "name": "💬 COMMUNITY",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "😂・memes", "type": "text"},
                    {"name": "🎉・community-events", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・Hangout", "type": "voice"},
                    {"name": "🎙️・Recording Room", "type": "voice"},
                    {"name": "🎮・Collab Voice", "type": "voice"},
                ],
            },
        ],
    },
    "esports": {
        "label": "Esports & Clan",
        "emoji": "⚔️",
        "description": "A competitive setup for a team, clan, or esports org",
        "color": discord.Color.dark_red(),
        "roles": [
            {"name": "👑 Team Owner", "color": discord.Color.gold(), "hoist": True, "mentionable": True},
            {"name": "🛡️ Coach", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "⚔️ Player", "color": discord.Color.dark_red(), "hoist": True, "mentionable": False},
            {"name": "🎯 Substitute", "color": discord.Color.orange(), "hoist": False, "mentionable": False},
            {"name": "👤 Fan", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text"},
                    {"name": "📜・rules", "type": "text"},
                    {"name": "🏆・tournament-results", "type": "text"},
                ],
            },
            {
                "name": "⚔️ TEAM",
                "channels": [
                    {"name": "📋・rosters", "type": "text"},
                    {"name": "📅・scrim-schedule", "type": "text"},
                    {"name": "🎯・strategy", "type": "text"},
                ],
            },
            {
                "name": "💬 COMMUNITY",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "😂・memes", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・Team Voice 1", "type": "voice"},
                    {"name": "🔊・Team Voice 2", "type": "voice"},
                    {"name": "🎯・Scrim Room", "type": "voice"},
                    {"name": "🏋️・Practice Room", "type": "voice"},
                ],
            },
        ],
    },
    "art": {
        "label": "Art & Design",
        "emoji": "🎨",
        "description": "A gallery-style server for artists to share and get feedback",
        "color": discord.Color.from_rgb(255, 105, 180),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "🎨 Artist", "color": discord.Color.from_rgb(255, 105, 180), "hoist": True, "mentionable": False},
            {"name": "👤 Member", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text"},
                    {"name": "📜・rules", "type": "text"},
                ],
            },
            {
                "name": "🎨 SHOWCASE",
                "channels": [
                    {"name": "🖼️・artwork-showcase", "type": "text"},
                    {"name": "🎬・process-and-wips", "type": "text", "topic": "Work-in-progress and process shots"},
                    {"name": "💡・critique-and-feedback", "type": "text"},
                ],
            },
            {
                "name": "💬 COMMUNITY",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "🎉・events-and-challenges", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・Art Lounge", "type": "voice"},
                    {"name": "🎨・Draw & Chat", "type": "voice"},
                ],
            },
        ],
    },
    "music": {
        "label": "Music",
        "emoji": "🎵",
        "description": "A server for musicians and music lovers to share and jam",
        "color": discord.Color.purple(),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "🎤 Musician", "color": discord.Color.purple(), "hoist": True, "mentionable": False},
            {"name": "🎧 Listener", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text"},
                    {"name": "📜・rules", "type": "text"},
                ],
            },
            {
                "name": "🎵 MUSIC",
                "channels": [
                    {"name": "🎧・now-playing", "type": "text"},
                    {"name": "🎤・share-your-music", "type": "text"},
                    {"name": "🎸・production-tips", "type": "text"},
                ],
            },
            {
                "name": "💬 COMMUNITY",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "😂・memes", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🎵・Listening Room", "type": "voice"},
                    {"name": "🎤・Jam Session", "type": "voice"},
                    {"name": "🔊・Lounge", "type": "voice"},
                ],
            },
        ],
    },
    "anime": {
        "label": "Anime & Manga",
        "emoji": "🌸",
        "description": "A community server for anime and manga fans",
        "color": discord.Color.from_rgb(255, 182, 193),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "🔧 Moderator", "color": discord.Color.orange(), "hoist": True, "mentionable": True},
            {"name": "🌸 Weeb", "color": discord.Color.from_rgb(255, 182, 193), "hoist": True, "mentionable": False},
            {"name": "👤 Member", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text"},
                    {"name": "📜・rules", "type": "text"},
                ],
            },
            {
                "name": "🌸 ANIME & MANGA",
                "channels": [
                    {"name": "📺・anime-discussion", "type": "text"},
                    {"name": "📖・manga-discussion", "type": "text"},
                    {"name": "🎨・fanart", "type": "text"},
                    {"name": "🌟・recommendations", "type": "text"},
                ],
            },
            {
                "name": "💬 COMMUNITY",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "😂・memes", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・Watch Party", "type": "voice"},
                    {"name": "💬・Lounge", "type": "voice"},
                ],
            },
        ],
    },
    "tech": {
        "label": "Tech & Developers",
        "emoji": "💻",
        "description": "A workspace-style server for developers to build and learn together",
        "color": discord.Color.dark_teal(),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "👨‍💻 Developer", "color": discord.Color.dark_teal(), "hoist": True, "mentionable": False},
            {"name": "🌱 Beginner", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text"},
                    {"name": "📜・rules", "type": "text"},
                ],
            },
            {
                "name": "💻 DEVELOPMENT",
                "channels": [
                    {"name": "🖥️・general-dev", "type": "text"},
                    {"name": "🐛・help-and-debugging", "type": "text"},
                    {"name": "🚀・showcase-projects", "type": "text"},
                    {"name": "📚・resources", "type": "text"},
                ],
            },
            {
                "name": "💬 COMMUNITY",
                "channels": [
                    {"name": "💬・general-chat", "type": "text"},
                    {"name": "😂・memes", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・Dev Lounge", "type": "voice"},
                    {"name": "🖥️・Pair Programming", "type": "voice"},
                ],
            },
        ],
    },
    "business": {
        "label": "Business & Startup",
        "emoji": "💼",
        "description": "A professional space for a startup, team, or networking group",
        "color": discord.Color.dark_gold(),
        "roles": [
            {"name": "🛡️ Admin", "color": discord.Color.red(), "hoist": True, "mentionable": True},
            {"name": "💼 Entrepreneur", "color": discord.Color.dark_gold(), "hoist": True, "mentionable": False},
            {"name": "🤝 Member", "color": discord.Color.light_grey(), "hoist": False, "mentionable": False},
        ],
        "categories": [
            {
                "name": "📋 INFORMATION",
                "channels": [
                    {"name": "📢・announcements", "type": "text"},
                    {"name": "📜・rules", "type": "text"},
                ],
            },
            {
                "name": "💼 BUSINESS",
                "channels": [
                    {"name": "📊・general-discussion", "type": "text"},
                    {"name": "💡・ideas-and-pitches", "type": "text"},
                    {"name": "🤝・networking", "type": "text"},
                    {"name": "📈・resources", "type": "text"},
                ],
            },
            {
                "name": "💬 COMMUNITY",
                "channels": [
                    {"name": "💬・off-topic", "type": "text"},
                ],
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "🔊・Meeting Room 1", "type": "voice"},
                    {"name": "🔊・Meeting Room 2", "type": "voice"},
                    {"name": "☕・Networking Lounge", "type": "voice"},
                ],
            },
        ],
    },
}
