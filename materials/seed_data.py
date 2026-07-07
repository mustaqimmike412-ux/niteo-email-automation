#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材库种子数据
完整保留全部原始业务内容，仅做结构化处理，无任何信息删减
"""

MATERIAL_LIBRARY = {
    # ============================================================
    # 一、自我简介与核心竞争优势
    # ============================================================
    "company_intro": {
        "intro_text": (
            "We are a leading global manufacturer of solar panels and a one-stop energy solution provider. "
            "We specialize in deep OEM/ODM customization services for world-renowned brands such as Amazon, Ring, Arlo, and EcoFlow. "
            "From high-quality conventional solar panels to pure-black, no-gridline \"High-Performance Cell\" panels, "
            "to custom-shaped, flexible panels and complete \"Solar + Storage + Charging\" systems, "
            "we are committed to combining cutting-edge manufacturing with a globalized supply chain "
            "to build the most competitive clean energy products for our clients."
        ),
        "advantages": {
            "high_performance_cell": {
                "name": "Core Technology: High-Performance Cell (Small Power Clients)",
                "scope": "small_power",
                "tech_features": (
                    "Surface no-gridline design (pure black appearance), "
                    "all conductive gridlines integrated on the back of the solar panel."
                ),
                "customer_value": [
                    "Higher power generation revenue: The unobstructed design absorbs more sunlight, significantly boosting generation and conversion efficiency.",
                    "Stronger low-light performance: Maintains stable power output even in suboptimal lighting conditions.",
                    "Ultimate visual aesthetics: The pure black appearance exudes a premium feel, making it easier to blend into high-end product design languages."
                ],
                "note": "In external communications, always use 'High-Performance Cell' to avoid copyright risks."
            },
            "oem_odm": {
                "name": "Top-Tier OEM/ODM Capability with Major Brand Endorsement (All Clients)",
                "scope": "all",
                "tech_features": (
                    "Deep OEM/ODM partner for Amazon, Ring, Arlo, EcoFlow, Jinko Solar and other global top-tier brands. "
                    "Supports highly flexible customization services covering custom shapes, lightweight versions, "
                    "flexible panels, and BIPV (Building Integrated Photovoltaics)."
                ),
                "customer_value": (
                    "Partnership with major brands means industry-leading quality control and manufacturing standards. "
                    "No matter how unique the client's product design, we can provide highly matched mold and production solutions, "
                    "significantly reducing the client's trial-and-error costs."
                )
            },
            "global_production": {
                "name": "Global Production Layout and Supply Chain Resilience (All Clients)",
                "scope": "all",
                "tech_features": "Factories located in China, Saudi Arabia, Indonesia, and Vietnam.",
                "customer_value": [
                    "Mitigating geopolitical trade risks through flexible multi-country factory allocation.",
                    "Flexible and efficient delivery: Nearby shipping and logistics optimization ensure the client's supply chain won't be disrupted by unexpected events in any single region."
                ]
            },
            "one_stop_solution": {
                "name": "One-Stop Full-Scenario Solutions with International Certifications (All Clients)",
                "scope": "all",
                "tech_features": (
                    "Product matrix from 1W to 200W multi-power solar panels (small power clients). "
                    "Supplier for Japanese energy giant DMM Energy. "
                    "Full international authoritative certifications: TUV, CE, UL, UKCA, ISO."
                ),
                "customer_value": (
                    "Clients don't need to shuttle between multiple suppliers. "
                    "From single component procurement to complete energy storage system construction, "
                    "we provide highly reliable products meeting stringent compliance requirements across all global regions, "
                    "saving clients the hassle of compliance audits."
                )
            },
            "ddp_logistics": {
                "name": "Worry-Free Logistics & Customs: DDP Delivery to USA (All Clients)",
                "scope": "all",
                "tech_features": (
                    "Complete DDP (Delivered Duty Paid) trade terms service (US DDP only, other countries not supported). "
                    "Supports direct shipment to Los Angeles and other designated US locations."
                ),
                "customer_value": [
                    "Ultimate convenience: We bear all risks, freight, import/export customs procedures and taxes during transit. Clients simply wait for delivery, no need to expend effort on complex cross-border logistics and customs affairs.",
                    "Transparent and controllable procurement costs: Door-to-door pricing gives clients full visibility into total costs, completely eliminating hidden taxes, customs fees, and logistics surcharges, significantly improving procurement experience and financial planning efficiency."
                ]
            }
        }
    },

    # ============================================================
    # 二、太阳能板宣传册素材
    # ============================================================
    "solar_panel_brochure": {
        "certifications": {
            "name": "International Certification Qualifications (All Clients)",
            "scope": "all",
            "content": (
                "International-level quality compliance: ISO9001, ISO14001 system certifications obtained, "
                "plus Amazon QSA audit and SA8000 certification. "
                "Products carry CE, RoHS, TUV, UKCA and other global mainstream certifications."
            )
        },
        "product_matrix": {
            "name": "Core PV Product Matrix (Large Power Clients)",
            "scope": "large_power",
            "categories": {
                "portable_flexible": {
                    "name": "Portable & Flexible PV Series",
                    "products": [
                        "Folding solar panels (100W-300W)",
                        "500W lightweight solar panels",
                        "Ultra-thin bendable flexible solar panels (200W-410W)"
                    ],
                    "customer_benefit": (
                        "Providing highly portable, easy-to-install reliable green power for RV, yacht, "
                        "balcony power generation, and outdoor camping users, "
                        "completely eliminating off-grid power anxiety."
                    )
                },
                "bipv_custom": {
                    "name": "Building PV & Custom Modules",
                    "products": [
                        "BIPV (Building Integrated Photovoltaics)",
                        "Solar tiles",
                        "Tracker-specific panels (for solar tracker clients)",
                        "Regular / colored modules"
                    ],
                    "customer_benefit": (
                        "BIPV and similar products seamlessly integrate clean energy with walls, roofs, or facades, "
                        "meeting architectural aesthetic needs while enhancing the building's overall environmental and commercial value."
                    )
                },
                "high_performance_custom": {
                    "name": "High-Performance Custom Modules",
                    "products": [
                        "High-Performance Cell modules",
                        "Double-glass modules",
                        "Various advanced customizations"
                    ],
                    "customer_benefit": (
                        "With superior photoelectric conversion efficiency, helping commercial, industrial, "
                        "and residential storage clients achieve higher system generation and investment returns."
                    )
                }
            }
        },
        "specialty_products": {
            "name": "Specialty End-Use Products (Specific Cattle Collar Clients)",
            "scope": "specific",
            "products": {
                "smart_cattle_collar": {
                    "name": "Smart Cattle Collar",
                    "description": (
                        "Designed for pasture management, with built-in GPS module and 4G communication. "
                        "Panel protected by market-standard glass, able to withstand high-intensity friction from daily cattle activity, "
                        "ensuring continuous device power and 30 days of stable battery life."
                    ),
                    "customer_benefit": (
                        "Helping ranchers track cattle activity range and behavioral patterns in real-time, "
                        "promptly identifying abnormalities such as illness or straying, "
                        "thereby significantly improving pasture management efficiency and cattle health."
                    )
                },
                "consumer_electronics_security": {
                    "name": "Consumer Electronics & Security Peripherals",
                    "description": (
                        "Supporting solar integration for outdoor cameras, video doorbells, solar backpacks, and other application products."
                    ),
                    "customer_benefit": (
                        "Providing continuous 'trickle charging' for smart devices, "
                        "significantly extending device battery life cycles and reducing maintenance and charging costs for end consumers."
                    )
                }
            }
        },
        "deep_oem_odm": {
            "name": "Deep OEM/ODM Customization Capability (All Clients)",
            "scope": "all",
            "content": (
                "This is the most critical element for winning B2B clients. "
                "Niteo has an experienced R&D and design team capable of comprehensive deep customization "
                "covering power, voltage, size, cables, controllers, appearance, and even brand logos."
            ),
            "customer_benefit": (
                "Clients don't need to build their own massive R&D teams to perfectly integrate "
                "Niteo's advanced PV technology into their own brand ecosystem, "
                "creating exclusive product lines highly tailored to their target audience."
            )
        }
    },

    # ============================================================
    # 三、储能宣传册素材
    # ============================================================
    "energy_storage_brochure": {
        "global_supply_chain": {
            "name": "Global Supply Chain Assurance (Large Power Clients)",
            "scope": "large_power",
            "core_info": "Mature production bases in Saudi Arabia, Indonesia, China, and Vietnam.",
            "customer_benefit": (
                "Multi-region production layout means stable, low-risk supply chains and faster delivery guarantees "
                "for global clients. No need to worry about delivery delays from any single region."
            )
        },
        "high_power_modules": {
            "name": "High-Power PV Modules (Large Power Clients)",
            "scope": "large_power",
            "core_info": (
                "Main power segments: 590W, 630W, and 720W, "
                "highly suitable for commercial/industrial rooftops and large-scale ground-mounted PV stations."
            ),
            "customer_benefit": (
                "By adopting high-efficiency High-Performance Cells, clients can maximize generation revenue "
                "within limited installation area, effectively shortening payback periods and improving overall project ROI."
            )
        },
        "commercial_ess": {
            "name": "Commercial & Industrial Energy Storage Systems (Large Power Clients)",
            "scope": "large_power",
            "core_info": (
                "110KWh and 215KWh solar-storage integrated cabinets; "
                "for ultra-large demands, 5015.96KWh 20-foot containerized liquid-cooling energy storage cabinets."
            ),
            "customer_benefit": (
                "Highly integrated intelligent temperature control (AC/fan) and composite fire protection systems "
                "(aerosol/perfluorohexanone), providing extremely high safety and stability for massive enterprise energy storage, "
                "significantly reducing post-operation maintenance costs and hidden risks."
            )
        },
        "residential_ess": {
            "name": "Residential Energy Storage & Inverters (Large Power Clients)",
            "scope": "large_power",
            "core_info": (
                "15KWh/30KWh LFP battery packs and 5KWh-20KWh low-voltage stackable batteries; "
                "paired with 6.2KW to 11KW hybrid inverters. "
                "In sufficient sunlight, a 15KWh system with 6.2KW inverter and 8x 580W panels charges in approximately 3.5 hours."
            ),
            "customer_benefit": (
                "Flexible stackable design and highly compatible inverters (perfectly compatible with mainstream brands) "
                "allow home users or overseas installers to customize systems based on actual budget and power needs, "
                "easily helping end users achieve energy self-sufficiency."
            )
        },
        "dc_charging_pile": {
            "name": "DC Charging Pile Solutions (Large Power Clients)",
            "scope": "large_power",
            "core_info": (
                "NPT 30K model with built-in 30kWh LFP battery, supporting up to 300A continuous charge/discharge, "
                "with ultra-long cycle life."
            ),
            "customer_benefit": (
                "Built-in long-life battery and active protection mechanisms provide stable and reliable power support "
                "for clients' EV charging networks, effectively mitigating grid impact even during peak demand periods."
            )
        }
    },

    # ============================================================
    # 四、Ring 客户案例素材
    # ============================================================
    "case_ring": {
        "name": "Ring Customer Case",
        "scope": "security_hardware",
        "products": {
            "high_power_outdoor_panel": {
                "name": "High-Power Outdoor Surveillance Solar Panel",
                "positioning": "Emphasizes universality and high power, suitable for eaves, walls, and other all-weather open lighting areas, solving continuous power supply needs for high-power surveillance devices (e.g., Spotlight Cam)."
            },
            "doorbell_solar_backplate": {
                "name": "Video Doorbell Exclusive Solar Charging Backplate",
                "positioning": "An invisible, compact micro-light charging device that perfectly fits the doorbell.",
                "specs": {
                    "dimensions": "14.8 cm x 9.3 cm x 1.3 cm",
                    "power_output": "0.57W, 5.2VDC",
                    "connection": "U-shaped custom terminal (Fork Connector) direct connection to doorbell back."
                },
                "design_challenges": (
                    "A high-difficulty non-standard custom structure. It serves directly as the doorbell's mounting backplate, "
                    "with volume extremely compressed. Within the extremely limited area, it still extends doorbell battery life by approximately 35%, "
                    "specifically designed for semi-shaded environments like front porches with limited lighting and high aesthetic requirements."
                )
            },
            "solar_camera_bracket": {
                "name": "Solar Panel + Camera 2-in-1 Wall Mount Bracket",
                "positioning": "A structural solution solving 'lighting angle vs. surveillance angle trade-off'.",
                "specs": {
                    "dimensions": "Approx. 7.2 cm x 21.5 cm x 7.5 cm (with retractable/multi-angle adjustable extension arm)",
                    "environmental_resistance": "Extremely rigorous weather resistance, withstanding up to 70°C extreme heat."
                },
                "design_challenges": (
                    "This is a non-electronic supporting hardware/plastic structural component. "
                    "It allows clients to install both camera and solar panel at a single drill point, "
                    "with the solar panel independently adjustable to track sunlight. "
                    "This demonstrates complete supporting R&D capability from PV electronic components to high-strength engineering structural components."
                )
            }
        },
        "core_advantages": [
            {
                "title": "Advanced BC No-Gridline Cell Technology",
                "content": (
                    "In our small solar panel designs, we master leading BC (Back Contact) cell application technology. "
                    "The panel surface has no conductive gridlines, which not only significantly boosts photoelectric conversion efficiency per unit area "
                    "(especially critical for size-constrained doorbell backplates), "
                    "but also delivers an ultimate pure black, minimalist industrial aesthetic, "
                    "perfectly matching the visual requirements of mid-to-high-end consumer electronics."
                )
            },
            {
                "title": "Multi-Scenario Integrated Customization (OEM/ODM)",
                "content": (
                    "From 4W standard panels to 0.57W micro non-standard custom panels, "
                    "to precision-adjustable 2-in-1 brackets, "
                    "we provide one-stop development of 'high-efficiency PV solutions + high-match structural components' "
                    "tailored to different hardware forms."
                )
            },
            {
                "title": "Stable & Convenient North American Delivery Network",
                "content": (
                    "With a complete cross-border logistics system, we offer DDP (Delivered Duty Paid) terms service "
                    "for direct shipment to Los Angeles and other US locations, "
                    "clearing import and customs barriers for North American clients, "
                    "achieving seamless end-to-end delivery."
                )
            }
        ],
        "workflow_rules": {
            "smart_home_hardware": {
                "condition": "Target client is a smart home hardware manufacturer",
                "priority_materials": ["doorbell_solar_backplate", "bc_no_gridline_tech"],
                "description": "Prioritize 'doorbell backplate' case and 'BC no-gridline technology'"
            },
            "traditional_security": {
                "condition": "Target client is a traditional security or engineering channel distributor",
                "priority_materials": ["high_power_outdoor_panel", "solar_camera_bracket", "ddp_delivery"],
                "description": "Prioritize 'high-power solar panel + 2-in-1 bracket' combination and 'Los Angeles DDP delivery' advantage"
            }
        }
    },

    # ============================================================
    # 五、Arlo 客户案例素材
    # ============================================================
    "case_arlo": {
        "name": "Arlo Customer Case",
        "scope": "security_hardware",
        "products": {
            "magnetic_solar_panel": {
                "name": "Arlo Premium Series Magnetic Solar Panel (for Ultra/Pro Series)",
                "positioning": (
                    "Outdoor power solution designed for Arlo Pro 3/4/5S, Ultra 1/2, and Floodlight "
                    "and other high-end, high-power flagship surveillance models."
                ),
                "specs": {
                    "power_output": "Approx. 2W (designed for all-weather 'trickle charging', aimed at maintaining battery level rather than fast charging from zero)",
                    "connection": "2.4m (8ft) outdoor waterproof magnetic charging cable",
                    "installation": "360-degree adjustable wall mount bracket with all-weather weatherproof design"
                },
                "design_challenges": (
                    "The core technical barrier lies in the customization of outdoor-grade magnetic connectors. "
                    "The magnetic design must ensure an extremely simple installation experience for end users (snap to charge), "
                    "while also guaranteeing absolute waterproofing, anti-corrosion, and short-circuit prevention at the connector "
                    "under extreme wind and rain conditions, "
                    "requiring extremely high precision in cable encapsulation and hardware mold manufacturing."
                )
            },
            "plug_in_solar_panel": {
                "name": "Arlo Essential Series Plug-in Solar Panel (for Essential Series Models)",
                "positioning": (
                    "High cost-performance, standardized continuous power solution for mainstream mid-range "
                    "and entry-level surveillance devices (Essential Outdoor / Essential XL, etc.)"
                ),
                "specs": {
                    "power_output": "1.2W - 2W",
                    "connection": "2.4m (8ft) integrated cable with USB-C or Micro-USB direct plug interface",
                    "structure": "High-strength rigid frame design ensuring long-term outdoor physical stability"
                },
                "design_challenges": (
                    "Uses more universal physical interfaces; the challenge lies in mold tolerance control at the interface "
                    "and waterproof gasket design, ensuring no water seepage after plugging in. "
                    "Meanwhile, under cost control constraints, ensuring the panel's long-term anti-UV capability and structural strength."
                )
            }
        },
        "core_advantages": [
            {
                "title": "Leading BC No-Gridline Cell Technology (Ultimate Aesthetics & High Efficiency)",
                "content": (
                    "In our solar panel designs, we master and apply leading BC (Back Contact) cell technology. "
                    "The panel front has no metal conductive gridlines, which not only effectively boosts photoelectric conversion efficiency "
                    "in low-light or semi-shaded environments, "
                    "but also gives the product a pure black, seamless minimalist industrial aesthetic, "
                    "perfectly matching the visual requirements of high-end smart hardware (like Arlo). "
                    "The standard glass protective layer also ensures extremely high durability in outdoor high-friction and sandstorm environments."
                )
            },
            {
                "title": "Top Security Brand OEM/ODM Experience",
                "content": (
                    "As a deep partner of global top security brands like Arlo and Ring, "
                    "we are proficient in the full range of PV power solutions from 'standardized Type-C interfaces' "
                    "to 'high-difficulty outdoor waterproof magnetic interfaces'. "
                    "We can provide perfectly adapted one-stop development for different camera structures."
                )
            },
            {
                "title": "Low-Cost Worry-Free North American Delivery (DDP Los Angeles)",
                "content": (
                    "With a mature cross-border delivery network, we offer DDP (Delivered Duty Paid) terms service "
                    "for direct shipment to Los Angeles. "
                    "North American clients can enjoy end-to-end supply chain services without handling complex import customs and logistics."
                )
            }
        ],
        "workflow_rules": {
            "high_end_hardware": {
                "condition": "Target client develops high-end hardware with magnetic or special interfaces",
                "priority_materials": ["magnetic_connector_waterproof_process", "bc_pure_black_high_efficiency"],
                "description": "Prioritize 'Arlo magnetic connector waterproof customization process' and 'BC pure black no-gridline cell aesthetics and high conversion advantages'"
            },
            "outdoor_demand": {
                "condition": "Target client has extremely high outdoor environment requirements (e.g., hunting cameras, farm surveillance)",
                "priority_materials": ["glass_protection_high_friction", "trickle_charging_stability"],
                "description": "Emphasize 'glass protection layer's high-strength friction resistance' and 'trickle charging's long-term stability'"
            },
            "north_america_buyer": {
                "condition": "Target is a North American domestic buyer",
                "priority_materials": ["ring_arlo_factory_endorsement", "los_angeles_ddp_delivery"],
                "description": "Mandatory call 'factory chosen by both Ring and Arlo' endorsement, highlight 'Los Angeles DDP delivery' logistics advantage"
            }
        }
    },

    # ============================================================
    # 六、Eufy 客户案例素材
    # ============================================================
    "case_eufy": {
        "name": "Eufy Customer Case",
        "scope": "security_hardware",
        "products": {
            "s340_dual_camera": {
                "name": "eufy SoloCam S340 (Dual Camera 360° Solar Surveillance Camera)",
                "positioning": "High-end all-around model with 360° rotation and dual-lens zoom.",
                "specs": {
                    "imaging": "3K wide-angle lens + 2K telephoto lens (supports 8x hybrid zoom)",
                    "solar_integration": "Detachable / adjustable-angle integrated solar panel",
                    "dynamic_performance": "Supports 360° horizontal rotation and 70° vertical flip"
                },
                "design_challenges": (
                    "The core lies in 'bracket and panel flexibility'. Since the body needs to rotate, "
                    "the panel must independently adjust its angle to avoid obstruction and capture light. "
                    "This 'split-type integration' design places extremely high demands on structural strength "
                    "and wiring durability, and is the mainstream trend for complex security terminals."
                )
            },
            "s3_pro_4k": {
                "name": "eufyCam S3 Pro (Flagship 4K Aurora Night Vision Camera)",
                "positioning": "Industry benchmark product focusing on ultimate image quality and low-light capture.",
                "specs": {
                    "imaging": "4K Ultra HD with MaxColor Vision technology (F1.0 large aperture sensor, true color in zero-light environments)",
                    "solar_system": "Built-in SolarPlus 2.0 high-efficiency integrated panel",
                    "smart_detection": "Radar + PIR dual detection technology"
                },
                "design_challenges": (
                    "As a flagship model, it requires higher conversion rates within extremely small panel areas "
                    "to support the high power consumption of 4K video processing and radar detection. "
                    "This is the optimal scenario for applying BC (Back Contact) high-efficiency cells, "
                    "delivering power output beyond conventional panels within the limited top space."
                )
            },
            "s220_compact": {
                "name": "eufy SoloCam S220 (Compact Entry-Level All-in-One)",
                "positioning": "Extremely minimalist, easy-to-install value-for-money choice.",
                "specs": {
                    "imaging": "2K resolution",
                    "form_factor": "Ultra-small body with fully integrated solar panel on top",
                    "protection_rating": "IP67 waterproof"
                },
                "design_challenges": (
                    "Due to the extremely small body, panel area is severely limited. "
                    "The design key is how to reduce self-power consumption through optimized circuit design, "
                    "and ensure high-performance encapsulation between the panel and injection-molded body, "
                    "achieving years of outdoor weather resistance."
                )
            }
        },
        "core_advantages": [
            {
                "title": "Visual Revolution Brought by BC Cell Technology",
                "content": (
                    "For brands like Eufy that emphasize 'industrial design sense', "
                    "we recommend applying the latest BC (Back Contact) no-gridline cell technology. "
                    "The panel surface has no metal gridlines at all, presenting a pure deep black, "
                    "with not only higher conversion efficiency but also perfect integration with the camera's black housing, "
                    "enhancing the product's 'technology premium'."
                )
            },
            {
                "title": "High-Strength Glass Protection Process",
                "content": (
                    "Unlike the easily worn ETFE lamination process on the market, "
                    "we use high-transmittance tempered glass protective layers. "
                    "This gives solar panels excellent friction resistance and anti-aging capabilities, "
                    "ensuring cameras maintain stable charging efficiency even in harsh outdoor environments "
                    "(such as sandstorms and extreme heat)."
                )
            },
            {
                "title": "Global Famous Brand OEM/ODM Endorsement",
                "content": (
                    "We long-term provide customized PV component development for Ring, Arlo, Eufy, "
                    "and power giant EcoFlow. We not only provide electronic components, "
                    "but also possess precision mold and structural integration capabilities for smart home hardware."
                )
            },
            {
                "title": "Mature B2B Delivery System (DDP Los Angeles)",
                "content": (
                    "We offer flexible international trade terms, supporting DDP service for direct shipment to Los Angeles. "
                    "We bear all import customs and taxes, helping clients achieve asset-light operations."
                )
            }
        ],
        "workflow_rules": {
            "pan_tilt_camera": {
                "condition": "Client makes panoramic / PTZ cameras",
                "priority_materials": ["s340_adjustable_panel_solution"],
                "description": "Focus on S340's adjustable panel solution"
            },
            "flagship_4k_camera": {
                "condition": "Client makes flagship 4K cameras",
                "priority_materials": ["bc_no_gridline_high_efficiency"],
                "description": "Focus on BC no-gridline high-efficiency technology"
            },
            "low_power_compact_camera": {
                "condition": "Client makes low-power compact cameras",
                "priority_materials": ["s220_ultimate_integration_process"],
                "description": "Focus on S220's ultimate integration process"
            }
        }
    },

    # ============================================================
    # 七、素材调用规则引擎
    # ============================================================
    "material_rules": {
        "by_power_type": {
            "small_power": {
                "mandatory": ["high_performance_cell", "oem_odm", "ddp_logistics", "one_stop_solution"],
                "brochure": ["certifications", "deep_oem_odm"],
                "cases": ["case_ring", "case_arlo", "case_eufy"]
            },
            "large_power": {
                "mandatory": ["oem_odm", "global_production", "one_stop_solution", "ddp_logistics"],
                "brochure": ["product_matrix", "certifications", "deep_oem_odm"],
                "cases": [],
                "storage": ["global_supply_chain", "high_power_modules", "commercial_ess", "residential_ess", "dc_charging_pile"]
            }
        },
        "by_track": {
            "security_hardware": {
                "case_priority": ["case_ring", "case_arlo", "case_eufy"],
                "tech_priority": ["bc_no_gridline", "glass_protection", "oem_odm_integration"],
                "delivery": "ddp_los_angeles"
            },
            "outdoor_portable": {
                "case_priority": [],
                "tech_priority": ["bc_no_gridline", "flexible_panel", "lightweight"],
                "delivery": "ddp_los_angeles"
            },
            "automation_gate": {
                "case_priority": [],
                "tech_priority": ["custom_size_power", "bc_no_gridline", "oem_odm_integration"],
                "delivery": "ddp_los_angeles"
            },
            "agriculture": {
                "case_priority": [],
                "tech_priority": ["high_power_modules", "durability", "global_production"],
                "delivery": "ddp_los_angeles"
            },
            "energy_storage": {
                "case_priority": [],
                "tech_priority": ["high_power_modules", "commercial_ess", "residential_ess"],
                "storage": ["global_supply_chain", "high_power_modules", "commercial_ess", "residential_ess", "dc_charging_pile"],
                "delivery": "ddp_los_angeles"
            }
        },
        "by_region": {
            "USA": {
                "mandatory_add": ["ddp_logistics"],
                "case_endorsement": "Ring/Arlo/Eufy shared factory endorsement"
            },
            "Europe": {
                "mandatory_add": ["one_stop_solution"],
                "emphasis": "TUV, CE, UKCA certifications"
            },
            "Australia": {
                "mandatory_add": ["one_stop_solution"],
                "emphasis": "CE, TUV certifications"
            }
        }
    }
}


def get_advantages_by_power_type(power_type: str) -> list:
    """根据功率类型获取优势列表"""
    library = MATERIAL_LIBRARY
    advantages = library["company_intro"]["advantages"]
    if power_type == "small_power":
        return [advantages["high_performance_cell"], advantages["oem_odm"],
                advantages["global_production"], advantages["ddp_logistics"]]
    else:
        return [advantages["oem_odm"], advantages["global_production"],
                advantages["one_stop_solution"], advantages["ddp_logistics"]]


def get_cases_by_track(track: str) -> list:
    """根据赛道获取案例列表"""
    library = MATERIAL_LIBRARY
    cases = []
    if "security" in track.lower() or "安防" in track:
        cases = [library["case_ring"], library["case_arlo"], library["case_eufy"]]
    return cases


def get_brochure_by_power_type(power_type: str) -> dict:
    """根据功率类型获取宣传册素材"""
    library = MATERIAL_LIBRARY
    brochure = library["solar_panel_brochure"]
    if power_type == "small_power":
        return {
            "certifications": brochure["certifications"],
            "specialty_products": brochure["specialty_products"],
            "deep_oem_odm": brochure["deep_oem_odm"]
        }
    else:
        return {
            "certifications": brochure["certifications"],
            "product_matrix": brochure["product_matrix"],
            "deep_oem_odm": brochure["deep_oem_odm"]
        }


def get_storage_brochure() -> dict:
    """获取储能宣传册素材（仅大功率客户）"""
    return MATERIAL_LIBRARY["energy_storage_brochure"]


def get_case_workflow_rules(track: str, region: str = "") -> dict:
    """根据赛道和地区获取案例调用规则"""
    library = MATERIAL_LIBRARY
    rules = library["material_rules"]
    track_rules = rules["by_track"].get(track, {})
    result = {
        "case_priority": track_rules.get("case_priority", []),
        "tech_priority": track_rules.get("tech_priority", []),
        "delivery": track_rules.get("delivery", "")
    }
    if region in rules["by_region"]:
        region_rules = rules["by_region"][region]
        result["mandatory_add"] = region_rules.get("mandatory_add", [])
        result["case_endorsement"] = region_rules.get("case_endorsement", "")
        result["emphasis"] = region_rules.get("emphasis", "")
    return result


def get_ring_case_for_email(customer_type: str) -> str:
    """
    根据客户类型获取Ring案例话术
    customer_type: 'smart_home' | 'traditional_security'
    """
    ring = MATERIAL_LIBRARY["case_ring"]

    if customer_type == "smart_home":
        product = ring["products"]["doorbell_solar_backplate"]
        advantage = ring["core_advantages"][0]  # BC technology
        return (
            f"For example, we developed a custom 0.57W solar charging backplate for Ring's video doorbell "
            f"({product['specs']['dimensions']}, {product['specs']['power_output']}). "
            f"Despite the extremely compact space, it extends battery life by ~35%. "
            f"{advantage['content']}"
        )
    else:
        product = ring["products"]["high_power_outdoor_panel"]
        bracket = ring["products"]["solar_camera_bracket"]
        advantage = ring["core_advantages"][2]  # DDP delivery
        return (
            f"We designed high-power outdoor solar panels and 2-in-1 wall mount brackets for Ring cameras, "
            f"withstanding up to 70°C extreme heat. "
            f"{advantage['content']}"
        )


def get_arlo_case_for_email(customer_type: str) -> str:
    """
    根据客户类型获取Arlo案例话术
    customer_type: 'high_end_hardware' | 'outdoor_demand' | 'north_america_buyer'
    """
    arlo = MATERIAL_LIBRARY["case_arlo"]

    if customer_type == "high_end_hardware":
        product = arlo["products"]["magnetic_solar_panel"]
        advantage = arlo["core_advantages"][0]  # BC technology
        return (
            f"For Arlo's Ultra and Pro series, we developed a magnetic solar panel with a 2.4m waterproof cable. "
            f"The magnetic connector ensures snap-to-charge simplicity while being fully waterproof in extreme weather. "
            f"{advantage['content']}"
        )
    elif customer_type == "outdoor_demand":
        advantage = arlo["core_advantages"][0]
        return (
            f"Our tempered glass protective layer ensures solar panels maintain stable charging efficiency "
            f"even in harsh outdoor environments like sandstorms and extreme heat. "
            f"{advantage['content']}"
        )
    else:  # north_america_buyer
        advantage = arlo["core_advantages"][2]  # DDP
        return (
            f"As the factory chosen by both Ring and Arlo, we offer DDP service for direct shipment to Los Angeles. "
            f"{advantage['content']}"
        )


def get_eufy_case_for_email(customer_type: str) -> str:
    """
    根据客户类型获取Eufy案例话术
    customer_type: 'pan_tilt' | 'flagship_4k' | 'compact'
    """
    eufy = MATERIAL_LIBRARY["case_eufy"]

    if customer_type == "pan_tilt":
        product = eufy["products"]["s340_dual_camera"]
        return (
            f"For eufy's SoloCam S340 with 360° rotation, we designed a detachable, adjustable-angle integrated solar panel. "
            f"The split-type integration design ensures the panel independently tracks sunlight while the camera rotates."
        )
    elif customer_type == "flagship_4k":
        product = eufy["products"]["s3_pro_4k"]
        advantage = eufy["core_advantages"][0]
        return (
            f"For eufy's 4K S3 Pro flagship camera, we applied BC (Back Contact) high-efficiency cell technology "
            f"to deliver superior power output within the limited top space, supporting 4K video and radar detection. "
            f"{advantage['content']}"
        )
    else:  # compact
        product = eufy["products"]["s220_compact"]
        return (
            f"For eufy's ultra-compact S220, we achieved full solar integration on top of a minimal body "
            f"with IP67 waterproof rating, optimizing circuit design to reduce self-power consumption "
            f"for years of outdoor durability."
        )
