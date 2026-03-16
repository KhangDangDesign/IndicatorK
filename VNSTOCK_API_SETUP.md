# vnstock API Rate Limit Solution

## 🚨 Problem
You're hitting vnstock's guest API limit of **20 requests/minute** when running weekly plan generation for 23 stocks.

## ✅ Solutions (Choose One)

### **Option 1: Free API Key (Recommended) - 60 requests/minute**

1. **Register for free**: https://vnstocks.com/login
2. **Get your API key** from the dashboard
3. **Add to your .env file**:
   ```bash
   echo "VNSTOCK_API_KEY=your_api_key_here" >> .env
   ```
4. **Restart the system** - weekly plans will now work smoothly

### **Option 2: Code-Based Rate Limiting (Already Implemented)**

I've already updated the code with:
- **Smaller batches**: 3 stocks per batch (was 5)
- **Longer delays**: 10 seconds between batches (was 1s)
- **Smart retry**: 30-50 second waits for rate limit errors
- **Max throughput**: ~18 requests/minute (within guest limits)

**Trade-off**: Weekly plan generation will take ~4-5 minutes instead of ~1 minute.

### **Option 3: Premium Membership - 180-600 requests/minute**

For heavy usage: https://vnstocks.com/insiders-program

## 🎯 Recommendation

**Get the free API key** - it's the perfect balance of speed and cost for your needs:
- ✅ **Free forever**
- ✅ **60 requests/minute** (3x guest limit)
- ✅ **Fast weekly plan generation** (~1 minute)
- ✅ **No code changes needed**

## 🔧 Current Status

Your system now has **automatic rate limit handling**:
- Detects Vietnamese rate limit messages
- Automatically waits when limits are hit
- Continues processing after delays
- **Weekly plans will complete successfully** (just slower)

## 📱 Next Steps

1. Get your free API key: https://vnstocks.com/login
2. Add `VNSTOCK_API_KEY=your_key` to `.env`
3. Enjoy fast, uninterrupted trading analysis! 🚀