import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import os
import json
import time
import random
from datetime import datetime, timedelta

# ランダムカラー選択用の関数
def get_random_color():
    """指定された5色からランダムで1色を選択"""
    colors = [0x808080, 0xFFFFCC, 0xFFFF00, 0xCCCC33, 0xCCFFCC]
    return random.choice(colors)

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

class VendingBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        intents.guilds = True
        super().__init__(command_prefix='!', intents=intents)

        # 半自動販売機システム（サーバーごと）
        self.vending_machines = {}  # {guild_id: {'products': {}, 'orders': {}, 'admin_channels': set(), 'next_order_id': 1}}

    async def on_ready(self):
        # ボット開始時刻を記録
        self.start_time = time.time()

        print(f'{self.user} がログインしました！')
        print(f'参加しているサーバー: {len(self.guilds)}個')

        # 参加している全サーバーの情報を表示
        for guild in self.guilds:
            print(f'- {guild.name} (ID: {guild.id})')

        # プレイ中ステータスを設定
        await self.update_status()

        # スラッシュコマンドを同期
        try:
            synced = await self.tree.sync()
            print(f'{len(synced)}個のスラッシュコマンドを同期しました')
        except Exception as e:
            print(f'スラッシュコマンドの同期エラー: {e}')

        # Webサーバーを開始
        await self.start_web_server()

    async def update_status(self):
        """プレイ中ステータスを更新"""
        try:
            guild_count = len(self.guilds)
            activity = discord.Game(name=f"半自動販売機 - {guild_count}サーバーで稼働中")
            await self.change_presence(activity=activity, status=discord.Status.online)
            print(f'ステータスを更新: 半自動販売機 - {guild_count}サーバーで稼働中')
        except Exception as e:
            print(f'ステータス更新エラー: {e}')

    async def on_guild_join(self, guild):
        """新しいサーバーに参加した時の処理"""
        print(f'新しいサーバーに参加しました: {guild.name} (ID: {guild.id})')

        # ステータスを更新
        await self.update_status()

        # 歓迎メッセージを送信
        try:
            # システムチャンネルまたは最初のテキストチャンネルを探す
            welcome_channel = guild.system_channel
            if not welcome_channel:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        welcome_channel = channel
                        break

            if welcome_channel:
                welcome_embed = discord.Embed(
                    title="半自動販売機Botを追加いただき、ありがとうございます！",
                    description=f"このBotは半自動販売機機能を提供します。\n\n"
                               "**主な機能：**\n"
                               "• 商品の管理\n"
                               "• 購入システム\n"
                               "• PayPay決済対応\n"
                               "• 自動DM配送\n\n"
                               "**設定方法：**\n"
                               "1. `/vending_setup` で管理者チャンネルを設定\n"
                               "2. `/add_product` で商品を追加\n"
                               "3. `/add_inventory` で在庫を追加\n"
                               "4. `/vending_panel` で販売機を設置\n\n"
                               "詳細は `/help` をご確認ください。",
                    color=get_random_color(),
                    timestamp=discord.utils.utcnow()
                )

                await welcome_channel.send(embed=welcome_embed)
                print(f'歓迎メッセージを {guild.name} に送信しました')

        except Exception as e:
            print(f'歓迎メッセージ送信エラー ({guild.name}): {e}')

    async def on_guild_remove(self, guild):
        """サーバーから退出した時の処理"""
        print(f'サーバーから退出しました: {guild.name} (ID: {guild.id})')

        # 関連データをクリーンアップ
        if guild.id in self.vending_machines:
            del self.vending_machines[guild.id]

        # ステータスを更新
        await self.update_status()

    def get_guild_vending_machine(self, guild_id):
        """サーバーの販売機データを取得（存在しない場合は初期化）"""
        if guild_id not in self.vending_machines:
            self.vending_machines[guild_id] = {
                'products': {},  # {product_id: {'name': str, 'price': int, 'description': str, 'stock': int, 'inventory': [str]}}
                'orders': {},    # {order_id: {'user_id': str, 'product_id': str, 'status': str, 'channel_id': int}}
                'admin_channels': set(),  # 管理者チャンネルのIDセット
                'achievement_channel': None,  # 実績チャンネルのID
                'next_order_id': 1
            }
        return self.vending_machines[guild_id]

    async def start_web_server(self):
        from aiohttp import web

        app = web.Application()

        # ヘルスチェックエンドポイント
        app.router.add_get('/', self.handle_health_check)
        app.router.add_get('/health', self.handle_health_check)
        app.router.add_get('/ping', self.handle_health_check)
        app.router.add_get('/status', self.handle_status_check)

        runner = web.AppRunner(app)
        await runner.setup()

        # Renderではポート10000を使用
        port = int(os.getenv('PORT', 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f'Webサーバーが http://0.0.0.0:{port} で開始されました')

    async def handle_health_check(self, request):
        """ヘルスチェックエンドポイント"""
        from aiohttp import web

        if self.is_ready():
            return web.Response(
                text="OK - 半自動販売機Bot is online", 
                status=200,
                content_type='text/plain'
            )
        else:
            return web.Response(
                text="Bot is not ready", 
                status=503,
                content_type='text/plain'
            )

    async def handle_status_check(self, request):
        """詳細なステータス情報を返すエンドポイント"""
        from aiohttp import web
        import json

        status_data = {
            "status": "online" if self.is_ready() else "offline",
            "guilds_count": len(self.guilds),
            "user": {
                "name": self.user.name if self.user else None,
                "id": self.user.id if self.user else None
            },
            "uptime": time.time() - getattr(self, 'start_time', time.time()),
            "timestamp": time.time()
        }

        return web.Response(
            text=json.dumps(status_data, indent=2),
            status=200,
            content_type='application/json'
        )

# ボットインスタンス
bot = VendingBot()

# スラッシュコマンド


@bot.tree.command(name='add_product', description='販売機に商品を追加します')
@app_commands.describe(
    product_id='商品ID（英数字）',
    name='商品名',
    price='価格',
    description='商品説明'
)
@app_commands.default_permissions(administrator=True)
async def add_product_slash(
    interaction: discord.Interaction,
    product_id: str,
    name: str,
    price: int,
    description: str
):
    """販売機に商品を追加"""
    if not product_id.replace('_', '').isalnum():
        await interaction.response.send_message(
            "❌ 商品IDは英数字のみ使用可能です。",
            ephemeral=True
        )
        return

    if price < 1:
        await interaction.response.send_message(
            "❌ 価格は1円以上で設定してください。",
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    vending_machine = bot.get_guild_vending_machine(guild_id)

    if product_id in vending_machine['products']:
        await interaction.response.send_message(
            f"❌ 商品ID「{product_id}」は既に存在します。",
            ephemeral=True
        )
        return

    # 商品をデータベースに追加
    vending_machine['products'][product_id] = {
        'name': name,
        'price': price,
        'description': description,
        'stock': 0,
        'inventory': []
    }

    # 在庫追加パネルを表示
    await interaction.response.send_modal(AddInventoryModal(product_id, name, price, description, guild_id))
    print(f'{interaction.user.name} が商品「{name}」を販売機に追加しました')

@bot.tree.command(name='add_inventory', description='商品に在庫アイテムを追加します')
@app_commands.describe(product_id='商品ID')
@app_commands.default_permissions(administrator=True)
async def add_inventory_slash(
    interaction: discord.Interaction,
    product_id: str
):
    """商品に在庫アイテムを追加"""
    guild_id = interaction.guild.id
    vending_machine = bot.get_guild_vending_machine(guild_id)

    if product_id not in vending_machine['products']:
        await interaction.response.send_message(
            f"❌ 商品ID「{product_id}」が見つかりません。",
            ephemeral=True
        )
        return

    product = vending_machine['products'][product_id]

    # 在庫追加パネルを表示
    await interaction.response.send_modal(AddInventoryOnlyModal(product_id, product['name'], guild_id))
    print(f'{interaction.user.name} が商品「{product["name"]}」の在庫追加パネルを開きました')



@bot.tree.command(name='vending_panel', description='販売機パネルを設置します')
@app_commands.describe(
    admin_channel='管理者チャンネル（必須）',
    achievement_channel='実績チャンネル（購入実績を自動送信、省略可）'
)
@app_commands.default_permissions(administrator=True)
async def vending_panel_slash(
    interaction: discord.Interaction, 
    admin_channel: discord.TextChannel,
    achievement_channel: discord.TextChannel = None
):
    """販売機パネルを設置"""
    guild_id = interaction.guild.id
    vending_machine = bot.get_guild_vending_machine(guild_id)

    if not vending_machine['products']:
        await interaction.response.send_message(
            "❌ 販売する商品がありません。先に `/add_product` で商品を追加してください。",
            ephemeral=True
        )
        return

    # 管理者チャンネルを設定
    vending_machine['admin_channels'].add(admin_channel.id)
    print(f'{interaction.user.name} がチャンネル {admin_channel.name} を販売機管理者チャンネルに設定しました')

    # 実績チャンネルが指定された場合は設定
    if achievement_channel:
        vending_machine['achievement_channel'] = achievement_channel.id
        print(f'{interaction.user.name} がチャンネル {achievement_channel.name} を実績チャンネルに設定しました')

    panel_embed = discord.Embed(
        title="🏪 半自動販売機",
        description="購入したい商品を選択してください。\n"
                   "購入後、PayPayリンクで決済し、確認後にDMで商品をお送りします。",
        color=get_random_color()
    )

    product_list = ""
    for product_id, product in vending_machine['products'].items():
        actual_stock = len(product.get('inventory', []))
        stock_status = f"在庫: {actual_stock}個" if actual_stock > 0 else "❌ 在庫切れ"
        product_list += f"**{product['name']}** - ¥{product['price']:,}\n{product['description']}\n{stock_status}\n\n"

    panel_embed.add_field(
        name="📋 商品一覧",
        value=product_list,
        inline=False
    )

    # 実績チャンネルが設定されている場合の表示
    if achievement_channel:
        panel_embed.add_field(
            name="📈 実績チャンネル", 
            value=f"購入実績が {achievement_channel.mention} に自動送信されます。",
            inline=False
        )

    panel_embed.set_footer(text="半自動販売機システム")

    view = VendingMachineView(guild_id)
    await interaction.response.send_message(embed=panel_embed, view=view)
    print(f'{interaction.user.name} が販売機パネルを設置しました')



# 販売機関連のViewクラス
class VendingMachineView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

        # 商品選択用のセレクトメニューを作成
        vending_machine = bot.get_guild_vending_machine(guild_id)
        options = []
        for product_id, product in vending_machine['products'].items():
            actual_stock = len(product.get('inventory', []))
            if actual_stock > 0:
                options.append(discord.SelectOption(
                    label=f"{product['name']} - ¥{product['price']:,}",
                    value=product_id,
                    description=product['description'][:100]
                ))

        if options:
            self.product_select.options = options
        else:
            self.remove_item(self.product_select)

    @discord.ui.select(
        placeholder="購入する商品を選択してください...",
        min_values=1,
        max_values=1
    )
    async def product_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        product_id = select.values[0]
        vending_machine = bot.get_guild_vending_machine(self.guild_id)
        product = vending_machine['products'].get(product_id)

        if not product:
            await interaction.response.send_message(
                "❌ 選択された商品が見つかりません。",
                ephemeral=True
            )
            return

        # 実際の在庫アイテム数をチェック
        inventory = product.get('inventory', [])
        if len(inventory) <= 0:
            await interaction.response.send_message(
                "❌ この商品は在庫切れです。",
                ephemeral=True
            )
            return

        # 注文IDを生成
        order_id = vending_machine['next_order_id']
        vending_machine['next_order_id'] += 1

        # 注文を記録
        vending_machine['orders'][str(order_id)] = {
            'user_id': str(interaction.user.id),
            'product_id': product_id,
            'status': 'pending_payment',
            'channel_id': interaction.channel.id,
            'timestamp': time.time(),
            'processed_by': None,
            'processed_at': None
        }

        # PayPayリンク入力モーダルを表示
        await interaction.response.send_modal(PayPayLinkModal(order_id, product, self.guild_id))
        print(f'{interaction.user.name} が商品「{product["name"]}」を注文しました (注文ID: {order_id})')

class AddInventoryOnlyModal(discord.ui.Modal, title='在庫アイテム一括追加'):
    def __init__(self, product_id, product_name, guild_id):
        super().__init__()
        self.product_id = product_id
        self.product_name = product_name
        self.guild_id = guild_id

    inventory_items = discord.ui.TextInput(
        label='在庫アイテムを入力してください（1行に1つずつ）',
        placeholder='アイテム1の内容\nアイテム2の内容\nアイテム3の内容\n...',
        style=discord.TextStyle.long,
        required=True,
        max_length=4000
    )

    async def on_submit(self, interaction: discord.Interaction):
        vending_machine = bot.get_guild_vending_machine(self.guild_id)
        product = vending_machine['products'].get(self.product_id)

        if not product:
            await interaction.response.send_message(
                f"❌ 商品ID「{self.product_id}」が見つかりません。",
                ephemeral=True
            )
            return

        # 改行で分割して在庫アイテムを追加
        inventory_lines = self.inventory_items.value.strip().split('\n')
        inventory_lines = [line.strip() for line in inventory_lines if line.strip()]

        if not inventory_lines:
            await interaction.response.send_message(
                "❌ 在庫アイテムが入力されていません。",
                ephemeral=True
            )
            return

        # 在庫アイテムを追加
        if 'inventory' not in product:
            product['inventory'] = []
        
        product['inventory'].extend(inventory_lines)
        product['stock'] = len(product['inventory'])

        inventory_embed = discord.Embed(
            title="✅ 在庫追加完了",
            description=f"商品「{self.product_name}」に在庫が追加されました。",
            color=get_random_color()
        )

        inventory_embed.add_field(name="商品ID", value=self.product_id, inline=True)
        inventory_embed.add_field(name="現在の在庫数", value=f"{product['stock']}個", inline=True)
        
        # 追加された在庫の一部を表示
        inventory_preview = "\n".join(inventory_lines[:3])
        if len(inventory_lines) > 3:
            inventory_preview += f"\n... 他{len(inventory_lines) - 3}個"
        
        inventory_embed.add_field(
            name="追加された在庫アイテム", 
            value=inventory_preview, 
            inline=False
        )

        await interaction.response.send_message(embed=inventory_embed)
        print(f'{interaction.user.name} が商品「{self.product_name}」に{len(inventory_lines)}個の在庫アイテムを追加しました')

class AddInventoryModal(discord.ui.Modal, title='在庫アイテム一括追加'):
    def __init__(self, product_id, product_name, price, description, guild_id):
        super().__init__()
        self.product_id = product_id
        self.product_name = product_name
        self.price = price
        self.description = description
        self.guild_id = guild_id

    inventory_items = discord.ui.TextInput(
        label='在庫アイテムを入力してください（1行に1つずつ）',
        placeholder='アイテム1の内容\nアイテム2の内容\nアイテム3の内容\n...',
        style=discord.TextStyle.long,
        required=True,
        max_length=4000
    )

    async def on_submit(self, interaction: discord.Interaction):
        vending_machine = bot.get_guild_vending_machine(self.guild_id)
        product = vending_machine['products'].get(self.product_id)

        if not product:
            await interaction.response.send_message(
                f"❌ 商品ID「{self.product_id}」が見つかりません。",
                ephemeral=True
            )
            return

        # 改行で分割して在庫アイテムを追加
        inventory_lines = self.inventory_items.value.strip().split('\n')
        inventory_lines = [line.strip() for line in inventory_lines if line.strip()]

        if not inventory_lines:
            await interaction.response.send_message(
                "❌ 在庫アイテムが入力されていません。",
                ephemeral=True
            )
            return

        # 在庫アイテムを追加
        product['inventory'].extend(inventory_lines)
        product['stock'] = len(product['inventory'])

        product_embed = discord.Embed(
            title="✅ 商品追加・在庫登録完了",
            description=f"商品「{self.product_name}」が販売機に追加され、在庫が登録されました。",
            color=get_random_color()
        )

        product_embed.add_field(name="商品ID", value=self.product_id, inline=True)
        product_embed.add_field(name="価格", value=f"¥{self.price:,}", inline=True)
        product_embed.add_field(name="在庫数", value=f"{product['stock']}個", inline=True)
        product_embed.add_field(name="説明", value=self.description, inline=False)
        
        # 追加された在庫の一部を表示
        inventory_preview = "\n".join(inventory_lines[:3])
        if len(inventory_lines) > 3:
            inventory_preview += f"\n... 他{len(inventory_lines) - 3}個"
        
        product_embed.add_field(
            name="追加された在庫アイテム", 
            value=inventory_preview, 
            inline=False
        )

        await interaction.response.send_message(embed=product_embed)
        print(f'{interaction.user.name} が商品「{self.product_name}」に{len(inventory_lines)}個の在庫アイテムを追加しました')

class PayPayLinkModal(discord.ui.Modal, title='決済リンク入力'):
    def __init__(self, order_id, product, guild_id):
        super().__init__()
        self.order_id = order_id
        self.product = product
        self.guild_id = guild_id

    paypay_link = discord.ui.TextInput(
        label='決済リンクを入力してください',
        placeholder='https://example.com/payment/link...',
        style=discord.TextStyle.long,
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        paypay_link = self.paypay_link.value.strip()

        # 基本的なリンク形式の検証（URLの形式のみチェック）
        if not paypay_link.startswith(('http://', 'https://')):
            await interaction.response.send_message(
                "❌ 無効なリンクです。正しいURLを入力してください。",
                ephemeral=True
            )
            return

        # 管理者チャンネルに通知を送信
        vending_machine = bot.get_guild_vending_machine(self.guild_id)
        for admin_channel_id in vending_machine['admin_channels']:
            try:
                admin_channel = bot.get_channel(admin_channel_id)
                if admin_channel:
                    await self.send_admin_notification(admin_channel, self.order_id, interaction.user, self.product, paypay_link)
            except Exception as e:
                print(f"管理者チャンネル通知エラー: {e}")

        # ユーザーに確認メッセージを送信
        purchase_embed = discord.Embed(
            title="🛒 商品注文完了",
            description=f"**{self.product['name']}** の注文を受け付けました。\n"
                       f"管理者が決済を確認次第、DMで商品をお送りします。",
            color=get_random_color()
        )

        purchase_embed.add_field(name="注文ID", value=f"#{self.order_id}", inline=True)
        purchase_embed.add_field(name="金額", value=f"¥{self.product['price']:,}", inline=True)
        purchase_embed.add_field(name="ステータス", value="決済確認待ち", inline=True)

        await interaction.response.send_message(embed=purchase_embed, ephemeral=True)

    async def send_admin_notification(self, channel, order_id, user, product, paypay_link):
        """管理者チャンネルに通知を送信"""
        admin_embed = discord.Embed(
            title="💰 新規注文通知",
            description="新しい商品注文が入りました。",
            color=get_random_color(),
            timestamp=discord.utils.utcnow()
        )

        admin_embed.add_field(name="注文ID", value=f"#{order_id}", inline=True)
        admin_embed.add_field(name="購入者", value=f"{user.mention}\n({user.name})", inline=True)
        admin_embed.add_field(name="商品", value=product['name'], inline=True)
        admin_embed.add_field(name="金額", value=f"¥{product['price']:,}", inline=True)
        admin_embed.add_field(name="決済リンク", value=f"[決済リンク]({paypay_link})", inline=False)

        admin_embed.set_thumbnail(url=user.display_avatar.url)

        view = AdminApprovalView(order_id)
        await channel.send(embed=admin_embed, view=view)

class AdminApprovalView(discord.ui.View):
    def __init__(self, order_id):
        super().__init__(timeout=3600)
        self.order_id = str(order_id)

    @discord.ui.button(label='商品送信', style=discord.ButtonStyle.success)
    async def approve_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        """注文を承認して商品を送信"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ この操作は管理者のみ実行できます。",
                ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        vending_machine = bot.get_guild_vending_machine(guild_id)
        order = vending_machine['orders'].get(self.order_id)

        if not order:
            await interaction.response.send_message(
                "❌ 注文が見つかりません。",
                ephemeral=True
            )
            return

        if order['status'] != 'pending_payment':
            await interaction.response.send_message(
                "❌ この注文は既に処理済みです。",
                ephemeral=True
            )
            return

        # 商品送信処理を直接実行
        await self.process_delivery(interaction, self.order_id)

    @discord.ui.button(label='注文キャンセル', style=discord.ButtonStyle.danger)
    async def reject_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        """注文をキャンセル"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ この操作は管理者のみ実行できます。",
                ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        vending_machine = bot.get_guild_vending_machine(guild_id)
        order = vending_machine['orders'].get(self.order_id)

        if not order:
            await interaction.response.send_message(
                "❌ 注文が見つかりません。",
                ephemeral=True
            )
            return

        # 注文をキャンセル状態に
        order['status'] = 'cancelled'

        # 購入者にDM送信
        try:
            user = await bot.fetch_user(int(order['user_id']))
            if user:
                cancel_embed = discord.Embed(
                    title="❌ 注文キャンセル",
                    description=f"注文 #{self.order_id} がキャンセルされました。\n"
                               "ご不明な点がございましたら、サーバー管理者にお問い合わせください。",
                    color=get_random_color()
                )
                await user.send(embed=cancel_embed)
        except Exception as e:
            print(f"キャンセル通知DM送信エラー: {e}")

        # 管理者メッセージを更新
        cancel_embed = discord.Embed(
            title="❌ 注文キャンセル完了",
            description=f"注文 #{self.order_id} をキャンセルしました。\n実行者: {interaction.user.mention}",
            color=get_random_color()
        )

        await interaction.response.edit_message(embed=cancel_embed, view=None)
        print(f'{interaction.user.name} が注文 #{self.order_id} をキャンセルしました')

    async def process_delivery(self, interaction: discord.Interaction, order_id: str):
        """商品配送処理"""
        guild_id = interaction.guild.id
        vending_machine = bot.get_guild_vending_machine(guild_id)
        order = vending_machine['orders'].get(order_id)

        if not order:
            await interaction.response.send_message(
                "❌ 注文が見つかりません。",
                ephemeral=True
            )
            return

        product_id = order['product_id']
        product = vending_machine['products'].get(product_id)

        if not product:
            await interaction.response.send_message(
                "❌ 商品が見つかりません。",
                ephemeral=True
            )
            return

        # 在庫から1つ取り出す
        inventory = product.get('inventory', [])
        if not inventory:
            await interaction.response.send_message(
                "❌ この商品の在庫がありません。",
                ephemeral=True
            )
            return

        # 最初の在庫アイテムを取り出し、在庫から削除
        item_content = inventory.pop(0)
        product['stock'] = len(inventory)

        # 注文を完了状態に
        order['status'] = 'completed'
        order['processed_by'] = str(interaction.user.id)
        order['processed_at'] = time.time()

        # 購入者にDMで商品を送信
        try:
            user = await bot.fetch_user(int(order['user_id']))
            
            # 事前チェック: ユーザーが存在するか
            if not user:
                await interaction.response.send_message(
                    "❌ 購入者のユーザー情報を取得できませんでした。",
                    ephemeral=True
                )
                return

            delivery_embed = discord.Embed(
                title="📦 商品お届け",
                description="ご注文いただいた商品をお届けします。",
                color=get_random_color(),
                timestamp=discord.utils.utcnow()
            )

            delivery_embed.add_field(name="注文ID", value=f"#{order_id}", inline=True)
            delivery_embed.add_field(name="商品名", value=product['name'], inline=True)
            delivery_embed.add_field(name="商品内容", value=item_content, inline=False)
            delivery_embed.set_footer(text="半自動販売機システム")

            await user.send(embed=delivery_embed)

            # 管理者メッセージを更新
            success_embed = discord.Embed(
                title="✅ 商品送信完了",
                description=f"注文 #{order_id} の商品を送信しました。\n"
                           f"実行者: {interaction.user.mention}\n"
                           f"残り在庫: {product['stock']}個",
                color=get_random_color(),
                timestamp=discord.utils.utcnow()
            )

            await interaction.response.edit_message(embed=success_embed, view=None)
            print(f'{interaction.user.name} が注文 #{order_id} の商品を送信しました (残り在庫: {product["stock"]}個)')

            # 実績チャンネルに通知を送信
            await self.send_achievement_notification(guild_id, order_id, user, product, interaction.user)

        except discord.Forbidden as e:
            # 送信失敗時は在庫を戻す
            inventory.insert(0, item_content)
            product['stock'] = len(inventory)
            order['status'] = 'pending_payment'

            error_embed = discord.Embed(
                title="❌ DM送信エラー",
                description="購入者にDMを送信できませんでした。",
                color=0xFF0000
            )
            error_embed.add_field(
                name="エラー原因",
                value="• ユーザーがDM受信を無効にしている\n• ボットがブロックされている\n• サーバーでDMが無効",
                inline=False
            )
            error_embed.add_field(
                name="対処方法",
                value="1. ユーザーにDM設定の確認を依頼\n2. サーバー内でのメンション通知も検討\n3. 在庫は元に戻されました",
                inline=False
            )
            
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            print(f"DM送信エラー (注文 #{order_id}): {e}")
            
        except discord.HTTPException as e:
            # 送信失敗時は在庫を戻す
            inventory.insert(0, item_content)
            product['stock'] = len(inventory)
            order['status'] = 'pending_payment'

            await interaction.response.send_message(
                f"❌ Discord APIエラーが発生しました:\n```{str(e)}```\n在庫は元に戻されました。",
                ephemeral=True
            )
            print(f"Discord APIエラー (注文 #{order_id}): {e}")
            
        except Exception as e:
            # 送信失敗時は在庫を戻す
            inventory.insert(0, item_content)
            product['stock'] = len(inventory)
            order['status'] = 'pending_payment'

            await interaction.response.send_message(
                f"❌ 予期しないエラーが発生しました:\n```{str(e)}```\n在庫は元に戻されました。",
                ephemeral=True
            )
            print(f"商品送信エラー (注文 #{order_id}): {e}")

    async def send_achievement_notification(self, guild_id, order_id, buyer, product, processor):
        """実績チャンネルに購入実績を送信"""
        try:
            vending_machine = bot.get_guild_vending_machine(guild_id)
            achievement_channel_id = vending_machine.get('achievement_channel')

            if not achievement_channel_id:
                return

            achievement_channel = bot.get_channel(achievement_channel_id)
            if not achievement_channel:
                return

            achievement_embed = discord.Embed(
                title="🎉 購入実績",
                description="商品が購入されました！",
                color=get_random_color(),
                timestamp=discord.utils.utcnow()
            )

            achievement_embed.add_field(
                name="購入者",
                value=f"{buyer.mention}\n({buyer.display_name})",
                inline=True
            )

            achievement_embed.add_field(
                name="商品",
                value=f"**{product['name']}**\n¥{product['price']:,}",
                inline=True
            )

            achievement_embed.add_field(
                name="注文ID",
                value=f"#{order_id}",
                inline=True
            )

            achievement_embed.add_field(
                name="処理者",
                value=f"{processor.mention}",
                inline=True
            )

            achievement_embed.add_field(
                name="残り在庫",
                value=f"{product['stock']}個",
                inline=True
            )

            achievement_embed.set_thumbnail(url=buyer.display_avatar.url)
            achievement_embed.set_footer(text="半自動販売機システム")

            await achievement_channel.send(embed=achievement_embed)

        except Exception as e:
            print(f"実績通知送信エラー: {e}")

def main():
    if not BOT_TOKEN:
        print("❌ DISCORD_BOT_TOKEN環境変数が設定されていません")
        return

    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"❌ ボットの起動に失敗しました: {e}")

if __name__ == "__main__":
    main()
