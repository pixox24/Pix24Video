"""
一键生成视频脚本 v2
主题：好设计 vs 坏设计 — UI 如何改变你的行为
用 fixed 模式，旁白直接写好，不依赖 LLM JSON 解析
输出到 ~/Desktop/视频/
"""
import asyncio
import sys
import os
from pathlib import Path

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

from pixelle_video import pixelle_video


async def main():
    print("🚀 初始化 Pixelle-Video...")
    await pixelle_video.initialize()
    print("✅ 初始化完成\n")

    output_dir = Path.home() / "Desktop" / "视频"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / "pixelle_video_output.mp4")

    # Fixed script mode: 自己写好旁白，直接生成
    script = (
        "每次打开App，那些精心设计的按钮和颜色都在悄悄引导你的选择\n"
        "所谓黑暗模式，就是让你稀里糊涂点了订阅，取消时却藏得无影无踪\n"
        "好的UI像贴心的朋友，比如屏幕时间功能，帮你管住刷手机的冲动\n"
        "无限滚动和红点提醒，其实是把老虎机塞进你口袋，一刷就停不下来\n"
        "设计师最懂你的弱点，利用损失厌恶心理让你不敢取消会员\n"
        "下次打开App时问问自己：这个设计是在帮我，还是在操纵我"
    )

    params = {
        "mode": "fixed",
        "split_mode": "line",
        "title": "好设计 vs 坏设计",
        "output_path": output_path,
        # TTS
        "tts_inference_mode": "local",
        "tts_voice": "zh-CN-YunjianNeural",
        "tts_speed": 1.2,
        # Template
        "frame_template": "1080x1920/image_default.html",
        "media_width": 1024,
        "media_height": 1024,
        "media_workflow": "bizyair/image_flux.json",
        # BGM
        "bgm_path": None,
        "bgm_volume": 0.15,
        # Prompt prefix
        "prompt_prefix": (
            "Minimalist black-and-white matchstick figure style illustration, "
            "clean lines, simple sketch, UI design concept art, clear metaphors, "
            "smartphone screens and interface elements as simple geometric shapes, "
            "white background, graphic design style"
        ),
    }

    print(f"📝 脚本: {len(script.split(chr(10)))} 句")
    print(f"📤 输出到: {output_path}")
    print(f"🎬 开始生成视频...\n")

    try:
        result = await pixelle_video.generate_video(
            text=script,
            **params
        )

        print(f"\n✅ 视频生成成功!")
        print(f"   📍 路径: {result.video_path}")
        print(f"   ⏱  时长: {result.duration:.2f}s")
        size_mb = result.file_size / (1024 * 1024)
        print(f"   💾 大小: {size_mb:.2f} MB")
        print(f"   🎞  分镜: {len(result.storyboard.frames)} 个")

    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await pixelle_video.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
