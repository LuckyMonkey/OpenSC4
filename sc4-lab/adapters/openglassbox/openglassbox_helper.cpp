// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Small process boundary for the external OpenGlassBox library. The JSON
// protocol lives in openglassbox_sidecar.py; this helper deliberately uses a
// tiny line protocol so the bridge has no third-party JSON dependency.

#include "OpenGlassBox/DijkstraRouter.hpp"
#include "OpenGlassBox/Path.hpp"
#include "OpenGlassBox/Simulation.hpp"

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <utility>
#include <cstdio>
#include <unistd.h>
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

    // --- SC4 city mode ----------------------------------------------------
    // A whole city on OpenGlassBox's own machinery: a generated .ogs ruleset
    // (resources, layers with diffusion/decay, agents, building rules), road
    // paths, buildings anchored to road nodes, and normal ticking. One grid
    // cell is one SC4 tile. These are OpenGlassBox behaviors, not SC4 rules.

    bool cityNew(std::istringstream& input, std::string& error)
    {
        std::uint32_t sizeU = 0u, sizeV = 0u, ticksPerMinute = 0u, seed = 0u;
        float cellSize = 0.0f;
        std::string script;
        if (!(input >> sizeU >> sizeV >> cellSize >> ticksPerMinute >> seed) || sizeU == 0u || sizeV == 0u
            || sizeU > 1024u || sizeV > 1024u || !(cellSize > 0.0f) || ticksPerMinute == 0u)
        {
            error = "invalid_city";
            return false;
        }
        std::getline(input >> std::ws, script);
        ogb::Config config;
        config.grid.cellSize = cellSize;
        config.grid.defaultCitySizeU = sizeU;
        config.grid.defaultCitySizeV = sizeV;
        config.time.ticksPerMinute = ticksPerMinute;
        config.randomSeed = seed;
        // One tick is one game minute here; reroute less often than the
        // per-second defaults so thousands of commuters stay affordable.
        config.routing.pathCheckTicks = 60u;
        config.routing.pathRecalcTicks = 240u;
        // A commuter with no reachable free destination gives up after two
        // game hours instead of forty; it would never arrive anyway.
        config.routing.agentGiveUpTicks = 120u;
        m_simulation = std::make_unique<ogb::Simulation>(config);
        m_simulation->setPaused(false);
        m_cellSize = cellSize;
        m_paths.clear();
        m_nodes.clear();
        if (!m_simulation->loadScriptFile(script))
        {
            error = "script " + m_simulation->formatScriptErrors();
            for (char& c : error)
                if (c == '\n')
                    c = ' ';
            return false;
        }
        m_city = &m_simulation->addCity("SC4", ogb::Vector3f(0.0f, 0.0f, 0.0f), sizeU, sizeV);
        // As the OpenGlassBox demo does: instantiate the script's layers and
        // give the city its default router (seeded from Config::randomSeed).
        for (auto const& item : m_simulation->getRuleset().getLayerTypes())
            m_city->addLayer(*item.second);
        ogb::installDijkstraRouters(*m_simulation);
        return true;
    }

    ogb::Node& nodeAt(ogb::Path& path, float x, float y)
    {
        auto key = std::make_pair(&path, std::make_pair(x, y));
        auto found = m_nodes.find(key);
        if (found != m_nodes.end())
            return *found->second;
        ogb::Node& node = path.addNode(ogb::Vector3f(x, y, 0.0f));
        m_nodes[key] = &node;
        return node;
    }

    bool road(std::istringstream& input)
    {
        std::string pathName, segmentName;
        float x1, y1, x2, y2;
        if (m_city == nullptr || !(input >> pathName >> segmentName >> x1 >> y1 >> x2 >> y2))
            return false;
        try
        {
            ogb::Path*& path = m_paths[pathName];
            if (path == nullptr)
                path = &m_city->addPath(m_simulation->getRuleset().getPathType(pathName));
            auto const& segmentType = m_simulation->getRuleset().getSegmentType(segmentName);
            path->addSegment(segmentType, nodeAt(*path, x1, y1), nodeAt(*path, x2, y2));
            return true;
        }
        catch (...)
        {
            return false;
        }
    }

    std::string building(std::istringstream& input)
    {
        std::string typeName;
        float x, y, reach;
        if (m_city == nullptr || !(input >> typeName >> x >> y >> reach))
            return "ERR invalid_building";
        try
        {
            auto const& type = m_simulation->getRuleset().getBuildingType(typeName);
            ogb::Node* best = nullptr;
            float bestDistance = std::numeric_limits<float>::max();
            for (auto const& item : m_nodes)
            {
                ogb::Vector3f const& p = item.second->getPosition();
                float d = std::hypot(p.x - x, p.y - y);
                if (d < bestDistance)
                {
                    bestDistance = d;
                    best = item.second;
                }
            }
            if (best != nullptr && bestDistance <= reach)
            {
                m_city->addBuilding(type, *best);
                return "OK anchored=1";
            }
            m_city->addBuilding(type, ogb::Vector3f(x, y, 0.0f));
            return "OK anchored=0";
        }
        catch (...)
        {
            return "ERR unknown_building_type";
        }
    }

    std::string layer(std::string const& name) const
    {
        ogb::Layer* found = (m_simulation == nullptr) ? nullptr : m_simulation->findLayer(name);
        if (found == nullptr || m_city == nullptr)
            return "ERR unknown_layer";
        ogb::CellRegion const& region = m_city->getRegion();
        std::ostringstream out;
        out << "OK u0=" << region.u0 << " v0=" << region.v0 << " w=" << region.getMaxU() - region.u0
            << " h=" << region.getMaxV() - region.v0 << " data=";
        std::uint64_t total = 0u;
        for (int32_t v = region.v0; v < region.getMaxV(); ++v)
            for (int32_t u = region.u0; u < region.getMaxU(); ++u)
            {
                std::uint32_t amount = found->getResource(ogb::Cell{ u, v });
                total += amount;
                out << amount << ((u + 1 < region.getMaxU() || v + 1 < region.getMaxV()) ? "," : "");
            }
        out << " total=" << total;
        return out.str();
    }

    std::string traffic() const
    {
        std::ostringstream out;
        out.precision(4);
        std::size_t count = 0u;
        std::ostringstream data;
        data.precision(4);
        for (auto const& item : m_paths)
            for (auto const& segment : item.second->getSegments())
            {
                ogb::Vector3f const& a = segment->getFrom().getPosition();
                ogb::Vector3f const& b = segment->getTo().getPosition();
                data << (count ? ";" : "") << a.x << ":" << a.y << ":" << b.x << ":" << b.y << ":"
                     << segment->getFlow() << ":" << segment->getSaturation();
                ++count;
            }
        out << "OK n=" << count << " data=" << data.str();
        return out.str();
    }

    std::string cityStats() const
    {
        if (m_city == nullptr)
            return "ERR no_city";
        auto const& clock = m_simulation->getClock();
        std::ostringstream out;
        out << "OK tick=" << clock.getTicks() << " day=" << clock.getDay() << " hour=" << clock.getHourOfDay()
            << " agents=" << m_city->getAgents().size() << " buildings=" << m_city->getBuildings().size();
        return out.str();
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
        if (command == "CITY_NEW")
        {
            std::string error;
            output = cityNew(input, error) ? cityStats() : "ERR " + error;
            return true;
        }
        if (command == "ROAD")
        {
            output = road(input) ? "OK" : "ERR invalid_road";
            return true;
        }
        if (command == "BUILDING")
        {
            output = building(input);
            return true;
        }
        if (command == "STEP")
        {
            std::uint64_t ticks = 0u;
            if (m_city == nullptr || !(input >> ticks) || ticks > 50000000u)
            {
                output = "ERR invalid_step";
                return true;
            }
            try
            {
                for (std::uint64_t i = 0u; i < ticks; ++i)
                    m_simulation->stepOneTick();
                output = cityStats();
            }
            catch (std::exception const& e)
            {
                output = std::string("ERR step_failed ") + e.what();
            }
            return true;
        }
        if (command == "LAYER")
        {
            std::string name;
            input >> name;
            output = layer(name);
            return true;
        }
        if (command == "TRAFFIC")
        {
            output = traffic();
            return true;
        }
        if (command == "CITY_STATS")
        {
            output = cityStats();
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
    float m_cellSize = 1.0f;
    std::map<std::string, ogb::Path*> m_paths;
    std::map<std::pair<ogb::Path*, std::pair<float, float>>, ogb::Node*> m_nodes;
};

} // namespace

int main()
{
    // The protocol owns the original stdout. OpenGlassBox writes diagnostics
    // (e.g. "Parsing script ...") to std::cout, which now goes to stderr so it
    // can never desynchronise request/response lines.
    int protocolFd = dup(STDOUT_FILENO);
    dup2(STDERR_FILENO, STDOUT_FILENO);
    FILE* protocol = fdopen(protocolFd, "w");
    Helper helper;
    std::string line;
    while (std::getline(std::cin, line))
    {
        std::string output;
        bool keepRunning = helper.handle(line, output);
        std::fputs(output.c_str(), protocol);
        std::fputc('\n', protocol);
        std::fflush(protocol);
        if (!keepRunning)
            break;
    }
    return 0;
}
