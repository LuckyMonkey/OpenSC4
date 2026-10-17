// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Small process boundary for the external OpenGlassBox library. The JSON
// protocol lives in openglassbox_sidecar.py; this helper deliberately uses a
// tiny line protocol so the bridge has no third-party JSON dependency.

#include "OpenGlassBox/Path.hpp"
#include "OpenGlassBox/Simulation.hpp"

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>

#ifndef OPENSC4_OGB_COMMIT
#define OPENSC4_OGB_COMMIT "unknown"
#endif

namespace
{

class Helper
{
public:
    Helper()
        : m_roadType("Road", 0xAAAAAA),
          m_segmentType("Dirt", 0xAAAAAA)
    {
        reset();
    }

    void reset()
    {
        m_simulation = std::make_unique<ogb::Simulation>();
        m_simulation->setPaused(false);
        m_city = &m_simulation->addCity("OpenSC4", ogb::Vector3f(0.0f, 0.0f, 0.0f), 32u, 32u);
    }

    bool addRoad(float x1, float y1, float x2, float y2)
    {
        if (m_city == nullptr)
            return false;
        ogb::Path* road = nullptr;
        auto const& paths = m_city->getPaths();
        auto found = paths.find("Road");
        if (found == paths.end())
            road = &m_city->addPath(m_roadType);
        else
            road = found->second.get();
        ogb::Node& from = road->addNode(ogb::Vector3f(x1, y1, 0.0f));
        ogb::Node& to = road->addNode(ogb::Vector3f(x2, y2, 0.0f));
        road->addSegment(m_segmentType, from, to);
        return true;
    }

    bool advance(float seconds)
    {
        if (seconds < 0.0f || !std::isfinite(seconds))
            return false;
        constexpr float ticksPerSecond = 20.0f;
        double requested = std::round(static_cast<double>(seconds) * ticksPerSecond);
        if (requested < 0.0 || requested > 2000000.0)
            return false;
        for (std::uint64_t index = 0u; index < static_cast<std::uint64_t>(requested); ++index)
            m_simulation->stepOneTick();
        return true;
    }

    bool setTick(std::uint64_t tick)
    {
        if (m_simulation == nullptr)
            return false;
        m_simulation->setTicks(tick);
        return true;
    }

    std::string snapshot() const
    {
        std::size_t paths = 0u;
        std::size_t nodes = 0u;
        std::size_t segments = 0u;
        if (m_city != nullptr)
        {
            paths = m_city->getPaths().size();
            for (auto const& item : m_city->getPaths())
            {
                nodes += item.second->getNodeCount();
                segments += item.second->getSegments().size();
            }
        }
        auto const& clock = m_simulation->getClock();
        std::ostringstream result;
        result << "OK"
               << " commit=" << OPENSC4_OGB_COMMIT
               << " tick=" << clock.getTicks()
               << " day=" << clock.getDay()
               << " hour=" << clock.getHourOfDay()
               << " minute=" << clock.getMinuteOfHour()
               << " cities=" << m_simulation->getCities().size()
               << " paths=" << paths
               << " nodes=" << nodes
               << " segments=" << segments;
        return result.str();
    }

    // --- SC4 budget slice -------------------------------------------------
    // Distilled SC4 monthly tax equation (docs/milestones/sc4-tax-distillation-v0.3.md),
    // with all state held in OpenGlassBox city globals and time on its clock.
    // OGB rules can only add/remove integer amounts, so the equation itself is
    // evaluated here; floats are stored as their IEEE bits to stay exact.

    static constexpr int kCategories = 12;

    static std::uint32_t floatBits(float value)
    {
        std::uint32_t bits = 0u;
        std::memcpy(&bits, &value, sizeof bits);
        return bits;
    }

    static float bitsFloat(std::uint32_t bits)
    {
        float value = 0.0f;
        std::memcpy(&value, &bits, sizeof value);
        return value;
    }

    void setGlobal(std::string const& name, std::uint32_t amount)
    {
        ogb::Resources& globals = m_city->getGlobals();
        std::uint32_t current = globals.getAmount(name);
        if (current > 0u)
            globals.removeResource(name, current);
        if (amount > 0u)
            globals.addResource(name, amount);
    }

    std::uint32_t global(std::string const& name) const
    {
        return m_city->getGlobals().getAmount(name);
    }

    bool budgetSet(std::istringstream& input)
    {
        long long funds = 0;
        long long expenses = 0;
        float mult = 0.0f;
        if (!(input >> funds >> expenses >> mult) || funds < 0 || funds > 0xFFFFFFFFLL
            || expenses < 0 || expenses > 0xFFFFFFFFLL || !std::isfinite(mult))
            return false;
        float rates[kCategories];
        long long bases[kCategories];
        for (float& rate : rates)
            if (!(input >> rate) || !std::isfinite(rate))
                return false;
        for (long long& base : bases)
            if (!(input >> base) || base < 0 || base > 0xFFFFFFFFLL)
                return false;
        setGlobal("SC4Funds", static_cast<std::uint32_t>(funds));
        setGlobal("SC4Expenses", static_cast<std::uint32_t>(expenses));
        setGlobal("SC4MultBits", floatBits(mult));
        for (int index = 0; index < kCategories; ++index)
        {
            setGlobal("SC4RateBits" + std::to_string(index), floatBits(rates[index]));
            setGlobal("SC4Base" + std::to_string(index), static_cast<std::uint32_t>(bases[index]));
        }
        return true;
    }

    std::string budgetMonth(std::uint32_t days)
    {
        // Same operation order as 0x006904C0 / 0x00692036: x87 extended
        // precision approximated by double, float factors, one truncation.
        double const mult = bitsFloat(global("SC4MultBits"));
        double const perMonth = 1.0f / 1200.0f;
        double total = 0.0;
        for (int index = 0; index < kCategories; ++index)
        {
            double rate = bitsFloat(global("SC4RateBits" + std::to_string(index)));
            total += static_cast<double>(global("SC4Base" + std::to_string(index))) * mult * rate * perMonth;
        }
        long long tax = static_cast<long long>(std::trunc(total));
        long long funds = static_cast<long long>(global("SC4Funds")) + tax
                          - static_cast<long long>(global("SC4Expenses"));
        bool clamped = funds < 0 || funds > 0xFFFFFFFFLL;
        if (funds < 0)
            funds = 0;
        if (funds > 0xFFFFFFFFLL)
            funds = 0xFFFFFFFFLL;
        setGlobal("SC4Funds", static_cast<std::uint32_t>(funds));
        setGlobal("SC4TaxIncome", static_cast<std::uint32_t>(tax < 0 ? 0 : tax));
        constexpr std::uint64_t ticksPerDay = 24u * 60u * 20u;
        m_simulation->setTicks(m_simulation->getClock().getTicks() + ticksPerDay * days);
        std::ostringstream result;
        result.precision(17);
        result << "OK tax=" << tax << " tax_exact=" << total << " funds=" << funds
               << " clamped=" << (clamped ? 1 : 0)
               << " tick=" << m_simulation->getClock().getTicks()
               << " day=" << m_simulation->getClock().getDay();
        return result.str();
    }

    std::string version() const
    {
        return std::string("OK commit=") + OPENSC4_OGB_COMMIT;
    }

    bool handle(std::string const& line, std::string& output)
    {
        std::istringstream input(line);
        std::string command;
        input >> command;
        if (command == "RESET")
        {
            reset();
            output = "OK";
            return true;
        }
        if (command == "VERSION")
        {
            output = version();
            return true;
        }
        if (command == "SNAPSHOT")
        {
            output = snapshot();
            return true;
        }
        if (command == "SET_TICK")
        {
            std::uint64_t tick = 0u;
            if (!(input >> tick) || !setTick(tick))
            {
                output = "ERR invalid_tick";
                return true;
            }
            output = snapshot();
            return true;
        }
        if (command == "ADVANCE")
        {
            float seconds = 0.0f;
            if (!(input >> seconds) || !advance(seconds))
            {
                output = "ERR invalid_seconds";
                return true;
            }
            output = snapshot();
            return true;
        }
        if (command == "ADD_ROAD")
        {
            float x1 = 0.0f;
            float y1 = 0.0f;
            float x2 = 0.0f;
            float y2 = 0.0f;
            if (!(input >> x1 >> y1 >> x2 >> y2) || !addRoad(x1, y1, x2, y2))
            {
                output = "ERR invalid_road";
                return true;
            }
            output = snapshot();
            return true;
        }
        if (command == "BUDGET_SET")
        {
            output = budgetSet(input) ? "OK funds=" + std::to_string(global("SC4Funds")) : "ERR invalid_budget";
            return true;
        }
        if (command == "BUDGET_MONTH")
        {
            std::uint32_t days = 0u;
            if (!(input >> days) || days == 0u || days > 31u)
            {
                output = "ERR invalid_days";
                return true;
            }
            output = budgetMonth(days);
            return true;
        }
        if (command == "QUIT")
        {
            output = "OK";
            return false;
        }
        output = "ERR unknown_command";
        return true;
    }

private:
    // Recipes are kept outside Simulation so their addresses remain stable for
    // every Path and Segment owned by the current city.
    ogb::PathType m_roadType;
    ogb::SegmentType m_segmentType;
    std::unique_ptr<ogb::Simulation> m_simulation;
    ogb::City* m_city = nullptr;
};

} // namespace

int main()
{
    Helper helper;
    std::string line;
    while (std::getline(std::cin, line))
    {
        std::string output;
        bool keepRunning = helper.handle(line, output);
        std::cout << output << '\n' << std::flush;
        if (!keepRunning)
            break;
    }
    return 0;
}
