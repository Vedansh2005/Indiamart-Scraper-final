# Quick Start Guide - IndiaMART Lead Scraper

## 🚀 **Ready to Run!**

Your scraper is now configured to collect **50 leads by default** (increased from 5). Here are all the ways you can run it:

### **Option 1: Double-click Batch Files (Easiest)**

- **`run_scraper.bat`** - Collects 50 leads (default)
- **`run_scraper_50_leads.bat`** - Collects exactly 50 leads  
- **`run_scraper_100_leads.bat`** - Collects 100 leads

### **Option 2: Command Line (More Control)**

```bash
# Collect 50 leads (default)
py scraper.py

# Collect 40 leads
py scraper.py --min-leads 40

# Collect 50 leads with specific product
py scraper.py --keyword "LED Bulbs" --min-leads 50

# Collect 100 leads
py scraper.py --min-leads 100

# Run in background (no browser UI)
py scraper.py --min-leads 50 --headless
```

### **Option 3: Custom Product + Lead Count**

```bash
# Search for "Steel Pipes" and collect 45 leads
py scraper.py --keyword "Steel Pipes" --min-leads 45

# Search for "Solar Panels" and collect 60 leads
py scraper.py --keyword "Solar Panels" --min-leads 60

# Search for "Textile" and collect 80 leads
py scraper.py --keyword "Textile" --min-leads 80
```

## 📱 **Before Running**

1. **Have your IndiaMART buyer account ready**
2. **Keep your phone nearby for OTP verification**
3. **Make sure Chrome browser is running**

## ⚡ **What Happens**

1. Chrome opens automatically
2. Navigates to IndiaMART buyer portal
3. Prompts for your mobile number
4. Sends OTP to your phone
5. You enter the OTP
6. Searches for products and collects leads
7. Exports results to `leads.csv`

## 📊 **Expected Results**

- **Default**: 50 leads in about 10-15 minutes
- **100 leads**: Takes about 20-30 minutes
- **All leads are sorted by relevancy score**
- **CSV file with company details, contact info, etc.**

## 🔧 **Troubleshooting**

- **Chrome won't start**: Run as administrator
- **No leads found**: Try different keywords
- **Login issues**: Check mobile number and OTP timing
- **Check logs**: Look in `logs/` folder for details

## 🎯 **Recommended First Run**

Start with the default 50 leads:
```bash
py scraper.py
```

This will search for "Cricket Ball" and collect 50 leads to test everything works correctly.

---

**Your scraper is now configured for 40-50+ leads by default!** 🎉

